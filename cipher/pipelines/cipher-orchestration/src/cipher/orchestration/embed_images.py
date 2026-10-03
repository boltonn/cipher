"""Image embedding workflow."""

import asyncio
import gc
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from time import perf_counter
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresImageRepository,
    PostgresLocationRepository,
)
from cipher.orchestration.exif_location import exif_location_create
from cipher.orchestration.image_heads import DEFAULT_MIN_STORED_SCORE, write_head_scores
from cipher.orchestration.image_size import DEFAULT_MIN_IMAGE_SIDE, is_below_min_side
from cipher.schemas.content.image import ImageCreate
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType
from cipher.utils.io import fetch_bytes_from_uri

if TYPE_CHECKING:
    from setfitcv.heads import TagHeads
    from setfitcv.model import CLIP

_EXECUTOR = ThreadPoolExecutor(max_workers=10)


def _sync_prepare_image(uri: str, preprocessor, min_image_side: int):
    """CPU worker: fetch and preprocess image; None when it's under `min_image_side`."""
    from PIL import Image
    from setfitcv.utils import ImageMetadataExtractor

    try:
        img_bytes = fetch_bytes_from_uri(uri)
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        if is_below_min_side(img, min_image_side):
            return None
        meta = {"width": img.width, "height": img.height}
        exif_meta = ImageMetadataExtractor.extract_metadata(img)
        if exif_meta:
            meta |= exif_meta
        pixel_values = preprocessor(images=img, return_tensors="pt")["pixel_values"]
        return pixel_values, meta
    except Exception as e:
        return e


async def _producer(
    queue: asyncio.Queue,
    session: "AsyncSession",
    batch_size: int,
    dataset_id: str | None,
    preprocessor,
    min_image_side: int,
):
    """Producer: fetch and prepare image batches."""
    from torch import cat as concat

    while True:
        enrichment_repo = PostgresEnrichmentRepository(session=session)
        batch = await enrichment_repo.get_pending_batch(
            enrichment_type=EnrichmentType.IMAGE_EMBEDDING,
            enrichable_type=EnrichableType.FILE,
            batch_size=batch_size,
            dataset_id=dataset_id,
            filetype_group_filter="image",
        )

        if not batch:
            await queue.put(None)
            break

        await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
        await session.commit()

        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(
                _EXECUTOR,
                _sync_prepare_image,
                item.resource["uri"],
                preprocessor,
                min_image_side,
            )
            for item in batch
        ]
        results = await asyncio.gather(*tasks)

        tensor_list, metadata_list, items = [], [], []
        failed: dict[str, str | Exception] = {}
        skipped: list[str] = []
        for item, res in zip(batch, results, strict=True):
            if res is None:
                skipped.append(item.enrichment.id)
            elif isinstance(res, Exception):
                failed[item.enrichment.id] = res
            else:
                tensor_list.append(res[0])
                metadata_list.append(res[1])
                items.append(item)

        await enrichment_repo.mark_skipped(dict.fromkeys(skipped, f"image under {min_image_side}px"))
        await enrichment_repo.mark_failed(failed)
        await session.commit()

        if tensor_list:
            await queue.put((concat(tensor_list, dim=0), metadata_list, items))


async def _consumer(
    queue: asyncio.Queue,
    session: "AsyncSession",
    model: "CLIP",
    commit_batch_size: int,
    stats: dict,
    heads: "TagHeads | None" = None,
):
    """Consumer: run inference (plus tag heads, in the same GPU pass, when given) and commit results."""
    pending_imgs, pending_locs, pending_data = [], [], []
    pending_scores: dict[str, dict[str, float]] = {}

    while True:
        batch_data = await queue.get()
        if batch_data is None:
            if pending_imgs:
                await _flush_to_db(session, pending_imgs, pending_locs, pending_data, heads, pending_scores)
            queue.task_done()
            break

        tensors, metas, items = batch_data

        start_inf = perf_counter()
        if heads is None:
            embeddings = await asyncio.to_thread(model.embed_imgs_batch, tensors)
        else:
            embeddings, scores = await asyncio.to_thread(model.embed_and_score_imgs_batch, tensors, heads)
            for item, row in zip(items, scores, strict=True):
                pending_scores[item.resource["sha256"]] = {
                    t: s for t, s in row.items() if s >= DEFAULT_MIN_STORED_SCORE
                }
        inf_ms = int((perf_counter() - start_inf) * 1000)

        for item, meta, emb in zip(items, metas, embeddings, strict=True):
            pending_imgs.append(
                ImageCreate(
                    id=item.resource["sha256"],
                    embedding=emb,
                    embedding_model=model.model_dir.name,
                    **meta,
                )
            )
            location = exif_location_create(
                meta, file_id=item.resource["id"], dataset_id=item.resource.get("dataset_id")
            )
            if location is not None:
                pending_locs.append(location)

        pending_data.append([i.enrichment.id for i in items])
        stats["count"] += len(items)

        if len(pending_imgs) >= commit_batch_size:
            await _flush_to_db(session, pending_imgs, pending_locs, pending_data, heads, pending_scores)
            pending_imgs.clear()
            pending_locs.clear()
            pending_data.clear()
            pending_scores.clear()
            gc.collect()

        queue.task_done()
        logger.info(f"Batch: {len(items)} images in {inf_ms}ms (Total: {stats['count']})")


async def _flush_to_db(session: "AsyncSession", images, locations, data, heads=None, scores=None):
    """Write embeddings, EXIF locations, enrichment status and (when heads ran) tag head scores to DB."""
    img_repo = PostgresImageRepository(session)
    loc_repo = PostgresLocationRepository(session)
    enr_repo = PostgresEnrichmentRepository(session)

    done = [idx for ids in data for idx in ids]

    # Two pending files can share a sha256 (identical image content at different
    # paths) and land in the same flush -- Postgres rejects an upsert batch that
    # targets the same conflict key twice, so keep one ImageCreate per id.
    unique_images = list({img.id: img for img in images}.values())
    await img_repo.upsert_image_batch(images=unique_images)
    if locations:
        await loc_repo.upsert_file_locations(rows=locations)
    await enr_repo.mark_completed_batch(enrichment_ids=done)
    await session.commit()
    if heads is not None and scores:
        image_ids = list(scores)
        await write_head_scores(session, heads=heads, image_ids=image_ids, scores=[scores[i] for i in image_ids])


async def embed_images(
    session: "AsyncSession",
    model: "CLIP",
    batch_size: int = 32,
    commit_batch_size: int = 128,
    dataset_id: str | None = None,
    heads: "TagHeads | None" = None,
    min_image_side: int = DEFAULT_MIN_IMAGE_SIDE,
) -> int:
    """Run image embedding pipeline, returning the number of images processed.

    With `heads`, every image is also scored by the tag heads in the same GPU pass.
    """
    if heads is not None and heads.embedding_model != model.model_dir.name:
        raise ValueError(
            f"Tag heads were trained on {heads.embedding_model!r} embeddings, not {model.model_dir.name!r}"
        )
    stats = {"count": 0}
    start_time = perf_counter()
    queue = asyncio.Queue(maxsize=4)

    # _producer and _consumer run concurrently via gather, so each needs its
    # own AsyncSession -- a single session isn't safe for concurrent use and
    # will corrupt its transaction state under interleaved commits/queries.
    engine = session.bind
    async with AsyncSession(engine, expire_on_commit=False) as producer_session:  # noqa: SIM117
        async with AsyncSession(engine, expire_on_commit=False) as consumer_session:
            await asyncio.gather(
                _producer(queue, producer_session, batch_size, dataset_id, model.img_preprocessor, min_image_side),
                _consumer(queue, consumer_session, model, commit_batch_size, stats, heads),
            )

    total_time = int((perf_counter() - start_time) * 1000)
    logger.success(f"Processed {stats['count']} images in {total_time}ms")
    return stats["count"]


async def queue_image_enrichments(
    session: "AsyncSession",
    dataset_id: str,
) -> None:
    """Queue image embedding enrichments for a dataset."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    await enrichment_repo.queue_enrichments_by_filter(
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.IMAGE_EMBEDDING,
        filetype_group="image",
    )
    await session.commit()


async def get_embedding_stats(
    session: "AsyncSession",
    dataset_id: str | None = None,
) -> dict:
    """Get enrichment stats for image embeddings."""
    enr_repo = PostgresEnrichmentRepository(session=session)
    return await enr_repo.get_enrichment_stats(
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.IMAGE_EMBEDDING,
    )


async def retry_failed_embeddings(
    session: "AsyncSession",
    dataset_id: str | None = None,
) -> int:
    """Reset failed enrichments back to pending."""
    enr_repo = PostgresEnrichmentRepository(session=session)
    count = await enr_repo.retry_failed_enrichments(
        enrichment_type=EnrichmentType.IMAGE_EMBEDDING,
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
    )
    await session.commit()
    return count


async def dedupe_pending_embeddings(
    session: "AsyncSession",
    dataset_id: str | None = None,
    batch_size: int = 100,
) -> int:
    """Resolve pending embeddings whose content has already been embedded.

    Cheap pre-pass: `Image` is keyed by sha256, so a pending file whose content
    was already embedded (by any file, any dataset) already shares that row --
    there's nothing to write, just mark the enrichment complete. Content
    without a match is left pending for `embed_images` to process normally.
    """
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    image_repo = PostgresImageRepository(session=session)

    total = 0
    while True:
        batch = await enrichment_repo.get_pending_batch(
            enrichment_type=EnrichmentType.IMAGE_EMBEDDING,
            enrichable_type=EnrichableType.FILE,
            batch_size=batch_size,
            dataset_id=dataset_id,
            filetype_group_filter="image",
        )
        if not batch:
            break

        resolved = []
        for item in batch:
            existing = await image_repo.get_image_by_id(item.resource["sha256"])
            if existing is not None and existing.embedding is not None:
                resolved.append(item.enrichment.id)

        if resolved:
            await enrichment_repo.mark_completed_batch(resolved)
            total += len(resolved)
            logger.info(f"Deduped {len(resolved)} image embeddings from existing content")

        # Always commit, even with nothing resolved: get_pending_batch's FOR
        # UPDATE SKIP LOCKED holds a lock on the whole batch until commit/
        # rollback, so skipping this when resolved is empty would leave
        # unresolved rows locked for the rest of the session's lifetime --
        # invisible to any other session's SKIP LOCKED scan, including
        # embed_images's own producer/consumer sessions right after this.
        await session.commit()

        if len(resolved) < len(batch):
            # Remaining pending items are genuinely new content; stop here
            # rather than re-fetching the same unresolved rows forever.
            break

    return total


async def embed_images_workflow(
    session: "AsyncSession",
    model: "CLIP",
    dataset_id: str,
    batch_size: int = 32,
    commit_batch_size: int = 128,
    heads: "TagHeads | None" = None,
    min_image_side: int = DEFAULT_MIN_IMAGE_SIDE,
) -> int:
    """Queue, dedupe, then embed (and optionally tag-score) a dataset's images. Returns images run through CLIP."""
    await queue_image_enrichments(session=session, dataset_id=dataset_id)
    await dedupe_pending_embeddings(session=session, dataset_id=dataset_id)
    return await embed_images(
        session=session,
        model=model,
        batch_size=batch_size,
        commit_batch_size=commit_batch_size,
        dataset_id=dataset_id,
        heads=heads,
        min_image_side=min_image_side,
    )
