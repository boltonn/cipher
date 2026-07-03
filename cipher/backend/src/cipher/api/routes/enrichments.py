from fastapi import APIRouter

from cipher.api.deps.postgres import EnrichmentDatastoreDep
from cipher.schemas.enrichment import (
    DatasetEnrichmentProgress,
    EnrichmentType,
    ProcessingStatus,
)

router = APIRouter(prefix="/enrichments", tags=["enrichments"])


@router.get(
    "/progress",
    response_model=DatasetEnrichmentProgress,
    response_model_by_alias=True,
)
async def get_enrichment_progress(
    datastore: EnrichmentDatastoreDep, enrichment_type: EnrichmentType, dataset_id: str
):
    """Get enrichment progress for a given dataset and enrichment type."""
    stats = await datastore.get_enrichment_stats(
        dataset_id=dataset_id,
        enrichment_type=enrichment_type,
    )
    counts = stats.get(enrichment_type, {})
    completed = counts.get(ProcessingStatus.COMPLETED, 0)
    total = sum(counts.values())
    return DatasetEnrichmentProgress(
        dataset_id=dataset_id,
        enrichment_type=enrichment_type,
        counts={k.value: v for k, v in counts.items()},
        total=total,
        completed=completed,
        progress=(completed / total) if total else 0.0,
    )
