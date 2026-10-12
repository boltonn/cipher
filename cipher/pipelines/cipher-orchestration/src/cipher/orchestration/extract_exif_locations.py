"""EXIF location extraction workflow.

Standalone (no ML, no model): for every image file in a dataset, read its EXIF
GPS and upsert a `location` row so geotagged photos show on the map. Depends
only on `File` rows existing -- runs independently of image embedding.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from time import perf_counter
from typing import TYPE_CHECKING

from loguru import logger
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresLocationRepository,
)
from cipher.orchestration.exif_location import exif_location_create
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType
from cipher.utils.uri import read_bytes

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_EXECUTOR = ThreadPoolExecutor(max_workers=10)


def _extract(uri: str) -> dict | None:
    """CPU worker: fetch an image and pull its EXIF metadata dict."""
    from PIL import Image
    from setfitcv.utils import ImageMetadataExtractor

    img = Image.open(BytesIO(read_bytes(uri))).convert("RGB")
    return ImageMetadataExtractor.extract_metadata(img) or {}


async def queue_exif_location_enrichments(session: "AsyncSession", dataset_id: str) -> int:
    """Queue EXIF-location enrichments for a dataset's image files."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    count = await enrichment_repo.queue_enrichments_by_filter(
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.EXIF_LOCATION,
        filetype_group="image",
    )
    await session.commit()
    return count


async def extract_exif_locations(
    session: "AsyncSession",
    dataset_id: str | None = None,
    batch_size: int = 50,
) -> int:
    """Run EXIF-location extraction over pending image files. Returns files processed."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    location_repo = PostgresLocationRepository(session=session)

    pending = await enrichment_repo.count_pending(
        enrichment_type=EnrichmentType.EXIF_LOCATION,
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        filetype_group_filter="image",
    )
    start = perf_counter()
    processed = 0
    located = 0

    with tqdm(total=pending, desc="EXIF locations") as progress:
        while True:
            batch = await enrichment_repo.get_pending_batch(
                enrichment_type=EnrichmentType.EXIF_LOCATION,
                enrichable_type=EnrichableType.FILE,
                batch_size=batch_size,
                dataset_id=dataset_id,
                filetype_group_filter="image",
            )
            if not batch:
                break

            await enrichment_repo.mark_processing([item.enrichment.id for item in batch])
            await session.commit()

            loop = asyncio.get_event_loop()
            results = await asyncio.gather(
                *(loop.run_in_executor(_EXECUTOR, _extract, item.resource["uri"]) for item in batch),
                return_exceptions=True,
            )

            locations, completed, failed = [], [], {}
            for item, res in zip(batch, results, strict=True):
                if isinstance(res, Exception):
                    logger.warning(f"EXIF read failed for file {item.resource['id']}: {res}")
                    failed[item.enrichment.id] = res
                    continue
                completed.append(item.enrichment.id)
                location = exif_location_create(
                    res, file_id=item.resource["id"], dataset_id=item.resource.get("dataset_id")
                )
                if location is not None:
                    locations.append(location)

            if locations:
                located += await location_repo.upsert_file_locations(rows=locations)
            await enrichment_repo.mark_completed_batch(completed)
            await enrichment_repo.mark_failed(failed)
            await session.commit()

            processed += len(completed)
            progress.update(len(batch))

    ms = int((perf_counter() - start) * 1000)
    logger.success(f"EXIF locations: {processed} files, {located} geotagged, in {ms}ms")
    return processed


async def extract_exif_locations_workflow(
    session: "AsyncSession",
    dataset_id: str,
    batch_size: int = 50,
) -> int:
    """Queue then run EXIF-location extraction for a dataset."""
    await queue_exif_location_enrichments(session=session, dataset_id=dataset_id)
    return await extract_exif_locations(session=session, dataset_id=dataset_id, batch_size=batch_size)


async def get_exif_location_stats(session: "AsyncSession", dataset_id: str | None = None) -> dict:
    """Enrichment stats for EXIF-location extraction."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    return await enrichment_repo.get_enrichment_stats(
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.EXIF_LOCATION,
    )


async def retry_failed_exif_locations(session: "AsyncSession", dataset_id: str | None = None) -> int:
    """Reset failed EXIF-location enrichments back to pending."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    count = await enrichment_repo.retry_failed_enrichments(
        enrichment_type=EnrichmentType.EXIF_LOCATION,
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
    )
    await session.commit()
    return count
