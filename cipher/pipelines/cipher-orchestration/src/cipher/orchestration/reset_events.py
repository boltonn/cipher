"""Reset the event layer for a dataset -- the undo for `extract-events`.

Mirrors `reset-entities` / `reset-text`: drops the dataset's extraction-built
`event` rows (participant / place rows cascade), keeping anything an analyst
authored (`extractor = manual`) or confirmed (`is_verified`), then clears the
EVENT_EXTRACTION enrichment rows so the next run reprocesses from scratch.
"""

from typing import TYPE_CHECKING

from loguru import logger

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresEventRepository,
)
from cipher.schemas.ingestion.enrichment import EnrichmentType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def reset_events(session: "AsyncSession", dataset_id: str) -> dict[str, int]:
    """Delete a dataset's extraction-built events. Returns per-table counts."""
    events = await PostgresEventRepository(session=session).delete_extracted_by_dataset_id(dataset_id)
    enrichments = await PostgresEnrichmentRepository(session=session).delete_by_type(
        dataset_id, EnrichmentType.EVENT_EXTRACTION
    )
    counts = {"events": events, "enrichments_cleared": enrichments}
    logger.success(f"Reset event layer for dataset {dataset_id}: {counts}")
    return counts
