from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from loguru import logger

from cipher.api.deps.access import DatasetAccessDep, DatasetIdQueryDep
from cipher.api.deps.postgres import EnrichmentDatastoreDep, get_session
from cipher.schemas._base.base import BaseModel
from cipher.schemas.graph.event import EVENT_FILE_TAG
from cipher.schemas.ingestion.enrichment import (
    ENRICHMENT_DEPENDENCIES,
    DatasetEnrichmentFailures,
    DatasetEnrichmentProgress,
    EnrichmentFailureReason,
    EnrichmentStageProgress,
    EnrichmentType,
    FailedEnrichment,
    ProcessingStatus,
)
from cipher.schemas.ingestion.estimation import ESTIMATE_ORDER

router = APIRouter(prefix="/enrichments", tags=["enrichments"])

# Order the pipeline steps are surfaced in: roughly the order they run.
PIPELINE_ORDER: tuple[EnrichmentType, ...] = ESTIMATE_ORDER

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


@router.post("/retry-failed")
async def retry_failed_enrichments(
    request: EnrichmentRunRequest, access: DatasetAccessDep, datastore: EnrichmentDatastoreDep
) -> dict[str, int]:
    """Put a dataset's failed rows for one analytic back to pending; the step's next run picks them up."""
    access.require(request.dataset_id)
    count = await datastore.retry_failed_enrichments(
        enrichment_type=request.enrichment_type, dataset_id=request.dataset_id
    )
    return {"count": count}


def _to_progress(
    dataset_id: str,
    enrichment_type: EnrichmentType,
    counts: dict[ProcessingStatus, int],
) -> DatasetEnrichmentProgress:
    completed = counts.get(ProcessingStatus.COMPLETED, 0)
    resolved = completed + counts.get(ProcessingStatus.SKIPPED, 0)  # skipped = deliberately not processed
    total = sum(counts.values())
    return DatasetEnrichmentProgress(
        dataset_id=dataset_id,
        enrichment_type=enrichment_type,
        counts={k.value: v for k, v in counts.items()},
        total=total,
        completed=completed,
        progress=(resolved / total) if total else 0.0,
    )


async def _event_stages(datastore, dataset_id: str) -> list[EnrichmentStageProgress]:
    """Event extraction's passes: `.ics` parsing, then (for email / document text) the gate and the LLM read."""
    rows = await datastore.gated_stage_counts(
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.EVENT_EXTRACTION,
        scored_tag=EVENT_FILE_TAG,
        calendar_filetype="ics",
    )

    def count(*, calendar: bool, status: ProcessingStatus | None = None, scored: bool | None = None) -> int:
        return sum(
            n
            for cal, row_status, has, n in rows
            if cal == calendar and status in (None, row_status) and scored in (None, has)
        )

    stages = []
    if calendar_total := count(calendar=True):
        stages.append(
            EnrichmentStageProgress(
                name="calendar",
                label="Calendar files (.ics)",
                total=calendar_total,
                completed=count(calendar=True, status=ProcessingStatus.COMPLETED),
                failed=count(calendar=True, status=ProcessingStatus.FAILED),
            )
        )
    text_total = count(calendar=False)
    gate_skipped = count(calendar=False, status=ProcessingStatus.SKIPPED)
    if gate_scored := count(calendar=False, scored=True):
        stages.append(
            EnrichmentStageProgress(
                name="gate",
                label="Gate (GLiNER + mail categories)",
                total=text_total,
                completed=gate_scored,
                skipped=gate_skipped,
            )
        )
    if text_total:
        stages.append(
            EnrichmentStageProgress(
                name="llm",
                label="LLM read",
                total=text_total - gate_skipped,
                completed=count(calendar=False, status=ProcessingStatus.COMPLETED),
                failed=count(calendar=False, status=ProcessingStatus.FAILED),
            )
        )
    return stages


async def _with_stages(datastore, progress: DatasetEnrichmentProgress) -> DatasetEnrichmentProgress:
    if progress.enrichment_type == EnrichmentType.EVENT_EXTRACTION and progress.total:
        progress.stages = await _event_stages(datastore, progress.dataset_id)
    return progress


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
    return await _with_stages(datastore, _to_progress(dataset_id, enrichment_type, stats.get(enrichment_type, {})))


@router.get(
    "/progress/all",
    response_model=list[DatasetEnrichmentProgress],
    response_model_by_alias=True,
)
async def get_dataset_enrichment_progress(datastore: EnrichmentDatastoreDep, dataset_id: DatasetIdQueryDep):
    """Progress for every analytic that has run against `dataset_id`, in pipeline order (others appended)."""
    stats = await datastore.get_enrichment_stats(dataset_id=dataset_id)
    ordered = [*PIPELINE_ORDER, *(t for t in stats if t not in PIPELINE_ORDER)]
    return [await _with_stages(datastore, _to_progress(dataset_id, t, stats[t])) for t in ordered if stats.get(t)]


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
                filename=item["file"].filename,
                path=item["file"].path,
                uri=item["file"].uri,
                filetype=item["file"].filetype,
                filetype_group=item["file"].filetype_group,
                mime_type=item["file"].mime_type,
                size=item["file"].size,
                error_message=item["enrichment"].error_message,
                retry_count=item["enrichment"].retry_count,
                date_updated=item["enrichment"].date_updated,
            )
            for item in items
        ],
    )
