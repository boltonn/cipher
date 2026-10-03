from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from loguru import logger

from cipher.api.deps.access import DatasetAccessDep, DatasetIdQueryDep
from cipher.api.deps.postgres import EnrichmentDatastoreDep, get_session
from cipher.schemas._base.base import BaseModel
from cipher.schemas.ingestion.enrichment import (
    ENRICHMENT_DEPENDENCIES,
    DatasetEnrichmentFailures,
    DatasetEnrichmentProgress,
    EnrichmentFailureReason,
    EnrichmentType,
    FailedEnrichment,
    ProcessingStatus,
)

router = APIRouter(prefix="/enrichments", tags=["enrichments"])

# Order the pipeline steps are surfaced in: roughly the order they run.
PIPELINE_ORDER: tuple[EnrichmentType, ...] = (
    EnrichmentType.TEXT_EXTRACTION,
    EnrichmentType.OCR,
    EnrichmentType.TEXT_EMBEDDING,
    EnrichmentType.IMAGE_EMBEDDING,
    EnrichmentType.EXIF_LOCATION,
    EnrichmentType.FACE_DETECTION,
    EnrichmentType.FACE_MATCHING,
    EnrichmentType.FACE_CLUSTERING,
    EnrichmentType.SELECTOR_EXTRACTION,
    EnrichmentType.ENTITY_EXTRACTION,
    EnrichmentType.RELATIONSHIP_EXTRACTION,
)

# Enrichments that need no ML model and are cheap enough to run in-process via
# BackgroundTasks when triggered from the UI.
_RUNNABLE: dict[EnrichmentType, str] = {
    EnrichmentType.EXIF_LOCATION: "EXIF location extraction",
}


class EnrichmentRunRequest(BaseModel):
    """Kick off an in-process enrichment run for one dataset."""

    dataset_id: str
    enrichment_type: EnrichmentType


class EnrichmentConfig(BaseModel):
    """Static pipeline metadata for clients: display order, hard prerequisites,
    and which analytics the API can trigger directly.
    """

    pipeline_order: list[EnrichmentType]
    dependencies: dict[EnrichmentType, list[EnrichmentType]]
    runnable: list[EnrichmentType]


@router.get("/config", response_model=EnrichmentConfig, response_model_by_alias=True)
async def get_enrichment_config() -> EnrichmentConfig:
    """The enrichment dependency graph + pipeline order, so clients don't hardcode it."""
    return EnrichmentConfig(
        pipeline_order=list(PIPELINE_ORDER),
        dependencies={etype: list(deps) for etype, deps in ENRICHMENT_DEPENDENCIES.items()},
        runnable=list(_RUNNABLE),
    )


async def _run_enrichment(enrichment_type: EnrichmentType, dataset_id: str) -> None:
    """Background worker: open a fresh session and run the matching workflow."""
    from cipher.orchestration.extract_exif_locations import extract_exif_locations_workflow

    try:
        async with get_session() as session:
            if enrichment_type == EnrichmentType.EXIF_LOCATION:
                count = await extract_exif_locations_workflow(session=session, dataset_id=dataset_id)
                logger.success(f"EXIF location run finished for {dataset_id}: {count} files")
    except Exception:
        logger.exception(f"Enrichment run failed: {enrichment_type} / {dataset_id}")


@router.post("/run", status_code=202)
async def run_enrichment(
    request: EnrichmentRunRequest, access: DatasetAccessDep, background_tasks: BackgroundTasks
) -> dict[str, str]:
    """Trigger a model-free enrichment for a dataset; it runs in the background."""
    access.require(request.dataset_id)
    if request.enrichment_type not in _RUNNABLE:
        raise HTTPException(
            status_code=400,
            detail=f"{request.enrichment_type} cannot be triggered from the API (run it via the CLI).",
        )
    background_tasks.add_task(_run_enrichment, request.enrichment_type, request.dataset_id)
    return {"status": "started", "detail": f"{_RUNNABLE[request.enrichment_type]} started for {request.dataset_id}"}


def _to_progress(
    dataset_id: str,
    enrichment_type: EnrichmentType,
    counts: dict[ProcessingStatus, int],
) -> DatasetEnrichmentProgress:
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


@router.get(
    "/progress",
    response_model=DatasetEnrichmentProgress,
    response_model_by_alias=True,
)
async def get_enrichment_progress(
    datastore: EnrichmentDatastoreDep,
    enrichment_type: Annotated[EnrichmentType, Query(alias="enrichmentType")],
    dataset_id: DatasetIdQueryDep,
):
    """Get enrichment progress for a given dataset and enrichment type."""
    stats = await datastore.get_enrichment_stats(
        dataset_id=dataset_id,
        enrichment_type=enrichment_type,
    )
    return _to_progress(dataset_id, enrichment_type, stats.get(enrichment_type, {}))


@router.get(
    "/progress/all",
    response_model=list[DatasetEnrichmentProgress],
    response_model_by_alias=True,
)
async def get_dataset_enrichment_progress(
    datastore: EnrichmentDatastoreDep, dataset_id: DatasetIdQueryDep
):
    """Progress for every analytic that has run against `dataset_id`, in pipeline order."""
    stats = await datastore.get_enrichment_stats(dataset_id=dataset_id)
    return [
        _to_progress(dataset_id, enrichment_type, stats[enrichment_type])
        for enrichment_type in PIPELINE_ORDER
        if stats.get(enrichment_type)
    ]


@router.get(
    "/failures",
    response_model=DatasetEnrichmentFailures,
    response_model_by_alias=True,
)
async def get_enrichment_failures(
    datastore: EnrichmentDatastoreDep,
    dataset_id: DatasetIdQueryDep,
    enrichment_type: Annotated[EnrichmentType, Query(alias="enrichmentType")],
    limit: int = 200,
    offset: int = 0,
):
    """Failed enrichments for a dataset + analytic: grouped reasons plus per-file detail."""
    total, items = await datastore.get_failed_enrichments(
        dataset_id=dataset_id,
        enrichment_type=enrichment_type,
        limit=limit,
        offset=offset,
    )
    reasons = await datastore.get_failure_reason_summary(dataset_id=dataset_id, enrichment_type=enrichment_type)
    return DatasetEnrichmentFailures(
        dataset_id=dataset_id,
        enrichment_type=enrichment_type,
        total=total,
        returned=len(items),
        reasons=[EnrichmentFailureReason(error_message=message, count=count) for message, count in reasons],
        items=[
            FailedEnrichment(
                id=item["enrichment"].id,
                enrichable_id=item["enrichment"].enrichable_id,
                filename=item["filename"],
                path=item["path"],
                error_message=item["enrichment"].error_message,
                retry_count=item["enrichment"].retry_count,
                date_updated=item["enrichment"].date_updated,
            )
            for item in items
        ],
    )
