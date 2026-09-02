"""Reset the entity layer for a dataset -- the undo for `extract-selectors`.

(And, later, for `extract-entities` / `resolve-entities` / `extract-relationships`.)
Mirrors `reset-text`: drops the dataset's `mention` rows, `entity_match` +
`entity_relationship_candidate` review queues, confirmed `entity_relationship`
edges, and every extraction-built `entity` (+ cascading detail) -- keeping
anything an analyst authored (`source = manual`) -- then clears the
SELECTOR / ENTITY / RELATIONSHIP extraction enrichment rows so the next run
reprocesses from scratch.
"""

from typing import TYPE_CHECKING

from loguru import logger

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresEntityMatchRepository,
    PostgresEntityRepository,
    PostgresGraphRepository,
    PostgresMentionRepository,
    PostgresRelationshipCandidateRepository,
)
from cipher.schemas.ingestion.enrichment import EnrichmentType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_ENRICHMENT_TYPES = (
    EnrichmentType.SELECTOR_EXTRACTION,
    EnrichmentType.ENTITY_EXTRACTION,
    EnrichmentType.RELATIONSHIP_EXTRACTION,
)


async def reset_entities(session: "AsyncSession", dataset_id: str) -> dict[str, int]:
    """Delete a dataset's extraction-built entity layer. Returns per-table counts."""
    mentions = await PostgresMentionRepository(session=session).delete_by_dataset_id(dataset_id)
    matches = await PostgresEntityMatchRepository(session=session).delete_by_dataset_id(dataset_id)
    candidates = await PostgresRelationshipCandidateRepository(session=session).delete_by_dataset_id(dataset_id)
    relationships = await PostgresGraphRepository(session=session).delete_by_dataset_id(dataset_id)
    entity_counts = await PostgresEntityRepository(session=session).delete_nonmanual_by_dataset_id(dataset_id)

    enrichment_repo = PostgresEnrichmentRepository(session=session)
    enrichments = 0
    for enrichment_type in _ENRICHMENT_TYPES:
        enrichments += await enrichment_repo.delete_by_type(dataset_id, enrichment_type)

    counts = {
        "mentions": mentions,
        "entities": entity_counts["entities"],
        "locations": entity_counts["locations"],
        "entity_matches": matches,
        "relationship_candidates": candidates,
        "relationships": relationships,
        "enrichments_cleared": enrichments,
    }
    logger.success(f"Reset entity layer for dataset {dataset_id}: {counts}")
    return counts
