"""Face detection workflow.

Depends only on `File` rows existing (any image-type file that's been
ingested), not on the CLIP image-embedding pipeline having run. A bare
`Image` metadata row (width/height, no embedding) is created on demand from
whichever file is processed first; `IMAGE_EMBEDDING` fills in the embedding
independently, whenever it runs.

Deliberately simple: one pending batch at a time, sequential inference. No
producer/consumer pipeline — face detection here is CPU/GPU-bound per image
rather than something that benefits from tensor batching the way CLIP does.
"""

from io import BytesIO
from time import perf_counter
from typing import TYPE_CHECKING

from loguru import logger
from PIL import Image as PILImage

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresFaceRepository,
    PostgresFileRepository,
    PostgresImageRepository,
)
from cipher.schemas.enrichment import EnrichableType, EnrichmentType
from cipher.schemas.face import FaceCreate, face_annotation_to_face_create
from cipher.schemas.image import ImageCreate
from cipher.utils.io import fetch_bytes_from_uri

if TYPE_CHECKING:
    from face.api.deps import AsyncInsightFaceModel
    from sqlalchemy.ext.asyncio import AsyncSession


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


async def _get_or_create_image(image_repo: PostgresImageRepository, file_id: str, img: PILImage.Image):
    """Fetch the file's Image row, creating a bare (embedding-less) one if needed.

    Never writes to an existing row, so it can't clobber an embedding that
    the CLIP pipeline has already computed.
    """
    image = await image_repo.get_image_by_file_id(file_id)
    if image is not None:
        return image
    return await image_repo.upsert_image(ImageCreate(file_id=file_id, width=img.width, height=img.height))


async def detect_faces(
    session: "AsyncSession",
    model: "AsyncInsightFaceModel",
    dataset_id: str | None = None,
    batch_size: int = 25,
) -> int:
    """Run face detection over pending files, returning the number processed."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    image_repo = PostgresImageRepository(session=session)
    face_repo = PostgresFaceRepository(session=session)

    total = 0
    start_time = perf_counter()

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

        await enrichment_repo.mark_processing([item.enrichment.id for item in batch])
        await session.commit()

        completed, failed, new_faces = [], [], []
        for item in batch:
            file_id, uri = item.resource["id"], item.resource["uri"]
            try:
                img = PILImage.open(BytesIO(fetch_bytes_from_uri(uri))).convert("RGB")
                image = await _get_or_create_image(image_repo, file_id, img)
                annotations = await model.infer_async(img)
                new_faces.extend(
                    face_annotation_to_face_create(
                        annotation,
                        image_id=image.id,
                        detector_model="insightface-buffalo_l",
                    )
                    for annotation in annotations
                )
                completed.append(item.enrichment.id)
            except Exception:
                logger.exception(f"Face detection failed for file {file_id}")
                failed.append(item.enrichment.id)

        if new_faces:
            await face_repo.add_faces_batch(new_faces)
        await enrichment_repo.mark_completed_batch(completed)
        if failed:
            await enrichment_repo.mark_failed_batch(failed, increment_retry=True)
        await session.commit()

        total += len(completed)
        logger.info(f"Detected faces in {len(completed)} files (total: {total})")

    total_time = int((perf_counter() - start_time) * 1000)
    logger.success(f"Face detection complete: {total} files in {total_time}ms")
    return total


async def _find_detected_duplicate(
    file_repo: PostgresFileRepository,
    image_repo: PostgresImageRepository,
    face_repo: PostgresFaceRepository,
    file_id: str,
    sha256: str,
):
    """Find another file's already-detected Image (with faces) sharing this content hash."""
    for duplicate_file in await file_repo.find_duplicates(sha256=sha256):
        if duplicate_file.id == file_id:
            continue
        image = await image_repo.get_image_by_file_id(duplicate_file.id)
        if image is None:
            continue
        faces = await face_repo.get_faces_with_embeddings_by_image(image.id)
        if faces:
            return image, faces
    return None, []


async def dedupe_pending_face_detections(
    session: "AsyncSession",
    dataset_id: str | None = None,
    batch_size: int = 100,
) -> int:
    """Resolve pending face detections whose content has already been processed.

    Cheap pre-pass: for each pending file, look for another file (any
    dataset) with the same sha256 whose faces have already been detected,
    and clone them instead of re-running InsightFace. Since the duplicate's
    width/height are reused too, this never even needs to read the file's
    bytes. Content without a match is left pending for `detect_faces`.
    """
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    file_repo = PostgresFileRepository(session=session)
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

        resolved, new_faces = [], []
        for item in batch:
            file_id, sha256 = item.resource["id"], item.resource["sha256"]
            duplicate_image, duplicate_faces = await _find_detected_duplicate(
                file_repo, image_repo, face_repo, file_id, sha256
            )
            if duplicate_image is None:
                continue
            image = await image_repo.get_image_by_file_id(file_id)
            if image is None:
                image = await image_repo.upsert_image(
                    ImageCreate(
                        file_id=file_id,
                        **duplicate_image.model_dump(exclude={"id", "file_id", "embedding", "embedding_model"}),
                    )
                )
            new_faces.extend(
                FaceCreate(
                    image_id=image.id,
                    **face.model_dump(
                        exclude={
                            "id",
                            "image_id",
                            "person_id",
                            "assignment_method",
                            "assignment_confidence",
                            "is_representative",
                            "is_primary",
                            "date_created",
                        }
                    ),
                )
                for face in duplicate_faces
            )
            resolved.append(item.enrichment.id)

        if new_faces:
            await face_repo.add_faces_batch(new_faces)
        if resolved:
            await enrichment_repo.mark_completed_batch(resolved)
            await session.commit()
            total += len(resolved)
            logger.info(f"Deduped face detection for {len(resolved)} files from existing content")

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
) -> int:
    """Queue, dedupe, then run face detection for a dataset, returning files processed."""
    await queue_face_detection_enrichments(session=session, dataset_id=dataset_id)
    await dedupe_pending_face_detections(session=session, dataset_id=dataset_id)
    return await detect_faces(session=session, model=model, dataset_id=dataset_id, batch_size=batch_size)


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
