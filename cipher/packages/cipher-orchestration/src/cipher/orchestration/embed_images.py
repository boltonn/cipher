"""Image embedding workflow."""

import asyncio
import gc
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from time import perf_counter
from typing import TYPE_CHECKING

from loguru import logger

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresFileRepository,
    PostgresImageRepository,
)
from cipher.schemas.enrichment import EnrichableType, EnrichmentType
from cipher.schemas.image import ImageCreate
from cipher.utils.io import fetch_bytes_from_uri

if TYPE_CHECKING:
    from setfitcv.model import CLIP
    from sqlalchemy.ext.asyncio import AsyncSession

_EXECUTOR = ThreadPoolExecutor(max_workers=10)


def _sync_prepare_image(uri: str, preprocessor):
    """CPU worker: fetch and preprocess image."""
    from PIL import Image
    from setfitcv.utils import ImageMetadataExtractor

    try:
        img_bytes = fetch_bytes_from_uri(uri)
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
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
            )
            for item in batch
        ]
        results = await asyncio.gather(*tasks)

        tensor_list, metadata_list, items, failed_ids = [], [], [], []
        for item, res in zip(batch, results, strict=True):
            if isinstance(res, Exception):
                failed_ids.append(item.enrichment.id)
                continue
            tensor_list.append(res[0])
            metadata_list.append(res[1])
            items.append(item)

        if tensor_list:
            await queue.put((concat(tensor_list, dim=0), metadata_list, items, failed_ids))


async def _consumer(
    queue: asyncio.Queue,
    session: "AsyncSession",
    model: "CLIP",
    commit_batch_size: int,
    stats: dict,
):
    """Consumer: run inference and commit results."""
    pending_imgs, pending_data = [], []

    while True:
        batch_data = await queue.get()
        if batch_data is None:
            if pending_imgs:
                await _flush_to_db(session, pending_imgs, pending_data)
            queue.task_done()
            break

        tensors, metas, items, fails = batch_data

        start_inf = perf_counter()
        embeddings = await asyncio.to_thread(model.embed_imgs_batch, tensors)
        inf_ms = int((perf_counter() - start_inf) * 1000)

        for item, meta, emb in zip(items, metas, embeddings, strict=True):
            pending_imgs.append(
                ImageCreate(
                    file_id=item.resource["id"],
                    embedding=emb,
                    embedding_model=model.model_dir.name,
                    **meta,
                )
            )

        pending_data.append({"completed": [i.enrichment.id for i in items], "failed": fails})
        stats["count"] += len(items)

        if len(pending_imgs) >= commit_batch_size:
            await _flush_to_db(session, pending_imgs, pending_data)
            pending_imgs.clear()
            pending_data.clear()
            gc.collect()

        queue.task_done()
        logger.info(f"Batch: {len(items)} images in {inf_ms}ms (Total: {stats['count']})")


async def _flush_to_db(session: "AsyncSession", images, data):
    """Write embeddings and enrichment status to DB."""
    img_repo = PostgresImageRepository(session)
    enr_repo = PostgresEnrichmentRepository(session)

    done = [idx for d in data for idx in d["completed"]]
    fails = [idx for d in data for idx in d["failed"]]

    await img_repo.upsert_image_batch(images=images)
    await enr_repo.mark_completed_batch(enrichment_ids=done)
    if fails:
        await enr_repo.mark_failed_batch(enrichment_ids=fails, increment_retry=True)
    await session.commit()


async def embed_images(
    session: "AsyncSession",
    model: "CLIP",
    batch_size: int = 32,
    commit_batch_size: int = 128,
    dataset_id: str | None = None,
) -> int:
    """Run image embedding pipeline, returning the number of images processed."""
    stats = {"count": 0}
    start_time = perf_counter()
    queue = asyncio.Queue(maxsize=4)

    await asyncio.gather(
        _producer(queue, session, batch_size, dataset_id, model.img_preprocessor),
        _consumer(queue, session, model, commit_batch_size, stats),
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


async def _find_embedded_duplicate(
    file_repo: PostgresFileRepository,
    image_repo: PostgresImageRepository,
    file_id: str,
    sha256: str,
):
    """Find another file's already-embedded Image sharing this content hash."""
    for duplicate_file in await file_repo.find_duplicates(sha256=sha256):
        if duplicate_file.id == file_id:
            continue
        image = await image_repo.get_image_by_file_id(duplicate_file.id)
        if image is not None and image.embedding is not None:
            return image
    return None


async def dedupe_pending_embeddings(
    session: "AsyncSession",
    dataset_id: str | None = None,
    batch_size: int = 100,
) -> int:
    """Resolve pending embeddings whose content has already been embedded elsewhere.

    Cheap pre-pass: for each pending file, look for another file (any
    dataset) with the same sha256 that already has an embedded Image, and
    copy its embedding instead of re-running CLIP. Content without a match
    is left pending for `embed_images` to process normally.
    """
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    file_repo = PostgresFileRepository(session=session)
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
            file_id, sha256 = item.resource["id"], item.resource["sha256"]
            duplicate_image = await _find_embedded_duplicate(file_repo, image_repo, file_id, sha256)
            if duplicate_image is None:
                continue
            await image_repo.upsert_image(
                ImageCreate(
                    file_id=file_id,
                    **duplicate_image.model_dump(exclude={"id", "file_id"}),
                )
            )
            resolved.append(item.enrichment.id)

        if resolved:
            await enrichment_repo.mark_completed_batch(resolved)
            await session.commit()
            total += len(resolved)
            logger.info(f"Deduped {len(resolved)} image embeddings from existing content")

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
) -> int:
    """Queue, dedupe, then embed a dataset's images. Returns images run through CLIP."""
    await queue_image_enrichments(session=session, dataset_id=dataset_id)
    await dedupe_pending_embeddings(session=session, dataset_id=dataset_id)
    return await embed_images(
        session=session,
        model=model,
        batch_size=batch_size,
        commit_batch_size=commit_batch_size,
        dataset_id=dataset_id,
    )
