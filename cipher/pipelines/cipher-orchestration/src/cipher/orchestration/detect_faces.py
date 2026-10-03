"""Face detection workflow.

Depends only on `File` rows existing (any image-type file that's been
ingested), not on the CLIP image-embedding pipeline having run. A bare
`Image` metadata row (width/height, no embedding) is created on demand from
whichever file is processed first; `IMAGE_EMBEDDING` fills in the embedding
independently, whenever it runs.

Uses the same producer/consumer split as `embed_images`: a thread pool
fetches and decodes images concurrently (I/O-bound) while the consumer runs
inference on whatever batch is ready (CPU/GPU-bound), so fetch latency for
the next batch overlaps with inference on the current one. Unlike CLIP,
InsightFace has no tensor-batched inference API, so the consumer still runs
one image at a time -- only the fetch stage is batched/concurrent.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from time import perf_counter
from typing import TYPE_CHECKING

from loguru import logger
from PIL import Image as PILImage
from sqlalchemy.ext.asyncio import AsyncSession
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresFaceRepository,
    PostgresImageRepository,
)
from cipher.orchestration.image_size import DEFAULT_MIN_IMAGE_SIDE, is_below_min_side
from cipher.schemas.content.image import ImageCreate
from cipher.schemas.identity.face import face_annotation_to_face_create
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType
from cipher.utils.io import fetch_bytes_from_uri

if TYPE_CHECKING:
    from face.api.deps import AsyncInsightFaceModel

_EXECUTOR = ThreadPoolExecutor(max_workers=10)


async def queue_face_detection_enrichments(
    session: "AsyncSession",
    dataset_id: str,
) -> int:
    """Queue face detection enrichments for a dataset's image files."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    count = await enrichment_repo.queue_enrichments_by_filter(
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.FACE_DETECTION,
        filetype_group="image",
    )
    await session.commit()
    return count


async def _get_or_create_image(image_repo: PostgresImageRepository, file_id: str, sha256: str, img: PILImage.Image):
    """Fetch this file's Image row (keyed by content hash).

    Creates a bare (embedding-less) one if needed. Never writes to an existing row, so
    it can't clobber an embedding that the CLIP pipeline has already computed.
    """
    image = await image_repo.get_image_by_id(sha256)
    if image is not None:
        return image
    return await image_repo.upsert_image(ImageCreate(id=sha256, width=img.width, height=img.height), file_id=file_id)


def _sync_load_image(uri: str) -> PILImage.Image:
    """CPU worker: fetch and decode an image."""
    return PILImage.open(BytesIO(fetch_bytes_from_uri(uri))).convert("RGB")


async def _producer(
    queue: asyncio.Queue,
    session: "AsyncSession",
    batch_size: int,
    dataset_id: str | None,
    min_image_side: int,
):
    """Producer: fetch pending batches and decode images concurrently; images under `min_image_side` are skipped."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)

    while True:
        batch = await enrichment_repo.get_pending_batch(
            enrichment_type=EnrichmentType.FACE_DETECTION,
            enrichable_type=EnrichableType.FILE,
            batch_size=batch_size,
            dataset_id=dataset_id,
            filetype_group_filter="image",
        )
        if not batch:
            await queue.put(None)
            break

        await enrichment_repo.mark_processing([item.enrichment.id for item in batch])
        await session.commit()

        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(_EXECUTOR, _sync_load_image, item.resource["uri"]) for item in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        images, items, skipped = [], [], []
        fetch_failed: dict[str, str | Exception] = {}
        for item, res in zip(batch, results, strict=True):
            if isinstance(res, Exception):
                logger.warning(f"Failed to fetch image for file {item.resource['id']}: {res}")
                fetch_failed[item.enrichment.id] = res
            elif is_below_min_side(res, min_image_side):
                skipped.append(item.enrichment.id)
            else:
                images.append(res)
                items.append(item)
        await enrichment_repo.mark_skipped(dict.fromkeys(skipped, f"image under {min_image_side}px"))
        await session.commit()

        await queue.put((images, items, fetch_failed, len(skipped)))


async def _consumer(
    queue: asyncio.Queue,
    session: "AsyncSession",
    model: "AsyncInsightFaceModel",
    progress: tqdm,
) -> int:
    """Consumer: run inference one image at a time (InsightFace has no batch API) and commit results."""
    image_repo = PostgresImageRepository(session=session)
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    face_repo = PostgresFaceRepository(session=session)

    # Faces are keyed by content hash (image_id == sha256), not by file. Track
    # which images this run has already detected so N pending files sharing one
    # content hash don't each append a full set of faces to the same image row.
    seen_image_ids: set[str] = set()

    total = 0
    while True:
        batch_data = await queue.get()
        if batch_data is None:
            queue.task_done()
            break

        images, items, failed, skipped = batch_data
        progress.update(len(failed) + skipped)

        completed, new_faces = [], []
        for item, img in zip(items, images, strict=True):
            file_id = item.resource["id"]
            try:
                image = await _get_or_create_image(image_repo, file_id, item.resource["sha256"], img)
                if image.id in seen_image_ids or await face_repo.image_has_faces(image.id):
                    # Content already detected (this run or a prior one) -- the
                    # faces are shared, so this file is done with nothing to write.
                    completed.append(item.enrichment.id)
                    progress.update(1)
                    continue
                annotations = await model.infer_async(img)
                new_faces.extend(
                    face_annotation_to_face_create(
                        annotation,
                        image_id=image.id,
                        detector_model="insightface-buffalo_l",
                        embedding_model="insightface-buffalo_l",
                    )
                    for annotation in annotations
                )
                seen_image_ids.add(image.id)
                completed.append(item.enrichment.id)
            except Exception as e:
                logger.exception(f"Face detection failed for file {file_id}")
                failed[item.enrichment.id] = e
            progress.update(1)

        if new_faces:
            await face_repo.add_faces_batch(new_faces)
            # Faces resembling one an analyst marked "not a face" (the same cat) are rejected on arrival.
            await face_repo.auto_reject_similar(image_ids=list({face.image_id for face in new_faces}))
        await enrichment_repo.mark_completed_batch(completed)
        await enrichment_repo.mark_failed(failed)
        await session.commit()

        total += len(completed)
        queue.task_done()

    return total


async def detect_faces(
    session: "AsyncSession",
    model: "AsyncInsightFaceModel",
    dataset_id: str | None = None,
    batch_size: int = 25,
    min_image_side: int = DEFAULT_MIN_IMAGE_SIDE,
) -> int:
    """Run face detection over pending files, returning the number processed."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    pending_count = await enrichment_repo.count_pending(
        enrichment_type=EnrichmentType.FACE_DETECTION,
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
    )

    start_time = perf_counter()
    queue = asyncio.Queue(maxsize=4)

    # _producer and _consumer run concurrently via gather, so each needs its
    # own AsyncSession -- a single session isn't safe for concurrent use and
    # will corrupt its transaction state under interleaved commits/queries.
    engine = session.bind
    async with AsyncSession(engine, expire_on_commit=False) as producer_session:  # noqa: SIM117
        async with AsyncSession(engine, expire_on_commit=False) as consumer_session:
            with tqdm(total=pending_count, desc="Detecting faces") as progress:
                _, total = await asyncio.gather(
                    _producer(queue, producer_session, batch_size, dataset_id, min_image_side),
                    _consumer(queue, consumer_session, model, progress),
                )

    total_time = int((perf_counter() - start_time) * 1000)
    logger.success(f"Face detection complete: {total} files in {total_time}ms")
    return total


async def dedupe_pending_face_detections(
    session: "AsyncSession",
    dataset_id: str | None = None,
    batch_size: int = 100,
) -> int:
    """Resolve pending face detections whose content has already been processed.

    Cheap pre-pass: `Image`/`Face` are keyed off content hash (`image_id` is
    the sha256), so a pending file whose content already has faces detected
    already shares them -- there's nothing to write, just mark the enrichment
    complete. Content without a match (or not yet embedded/detected at all)
    is left pending for `detect_faces`.
    """
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    image_repo = PostgresImageRepository(session=session)
    face_repo = PostgresFaceRepository(session=session)

    total = 0
    while True:
        batch = await enrichment_repo.get_pending_batch(
            enrichment_type=EnrichmentType.FACE_DETECTION,
            enrichable_type=EnrichableType.FILE,
            batch_size=batch_size,
            dataset_id=dataset_id,
            filetype_group_filter="image",
        )
        if not batch:
            break

        resolved = []
        for item in batch:
            image = await image_repo.get_image_by_id(item.resource["sha256"])
            if image is None:
                continue
            faces = await face_repo.get_faces_with_embeddings_by_image(image.id)
            if faces:
                resolved.append(item.enrichment.id)

        if resolved:
            await enrichment_repo.mark_completed_batch(resolved)
            total += len(resolved)
            logger.info(f"Deduped face detection for {len(resolved)} files from existing content")

        # Always commit, even with nothing resolved: get_pending_batch's FOR
        # UPDATE SKIP LOCKED holds a lock on the whole batch until commit/
        # rollback, so skipping this when resolved is empty would leave
        # unresolved rows locked for the rest of the session's lifetime --
        # invisible to any other session's SKIP LOCKED scan, including
        # detect_faces's own producer/consumer sessions right after this.
        await session.commit()

        if len(resolved) < len(batch):
            # Remaining pending items are genuinely new content; stop here
            # rather than re-fetching the same unresolved rows forever.
            break

    return total


async def detect_faces_workflow(
    session: "AsyncSession",
    model: "AsyncInsightFaceModel",
    dataset_id: str,
    batch_size: int = 25,
    min_image_side: int = DEFAULT_MIN_IMAGE_SIDE,
) -> int:
    """Queue, dedupe, then run face detection for a dataset, returning files processed."""
    await queue_face_detection_enrichments(session=session, dataset_id=dataset_id)
    await dedupe_pending_face_detections(session=session, dataset_id=dataset_id)
    return await detect_faces(
        session=session, model=model, dataset_id=dataset_id, batch_size=batch_size, min_image_side=min_image_side
    )


async def get_face_detection_stats(
    session: "AsyncSession",
    dataset_id: str | None = None,
) -> dict:
    """Get enrichment stats for face detection."""
    enr_repo = PostgresEnrichmentRepository(session=session)
    return await enr_repo.get_enrichment_stats(
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.FACE_DETECTION,
    )
