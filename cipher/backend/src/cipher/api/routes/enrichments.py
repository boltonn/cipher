from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from loguru import logger

from cipher.api.deps.access import DatasetAccessDep, DatasetIdQueryDep
from cipher.api.deps.postgres import EnrichmentDatastoreDep, EnrichmentRunDatastoreDep, get_session
from cipher.schemas._base.base import BaseModel
from cipher.schemas.graph.event import EVENT_FILE_TAG
from cipher.schemas.ingestion.enrichment import (
    ENRICHMENT_DEPENDENCIES,
    RESOLUTION_RUN,
    DatasetEnrichmentFailures,
    DatasetEnrichmentProgress,
    EnrichmentFailureReason,
    EnrichmentStageProgress,
    EnrichmentType,
    FailedEnrichment,
    ProcessingStatus,
    SweepRun,
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
    """Static pipeline metadata for clients.

    Display order, hard prerequisites, and which analytics the API can trigger directly.
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


# Dataset-wide passes with no per-file rows: their progress is their latest recorded run.
_RUN_TRACKED = (EnrichmentType.FACE_MATCHING, EnrichmentType.FACE_CLUSTERING)
# A stopped run left its work queued: it reads as waiting, not failed.
_RUN_STATUS = {
    "completed": ProcessingStatus.COMPLETED,
    "failed": ProcessingStatus.FAILED,
    "stopped": ProcessingStatus.PENDING,
    "cancelled": ProcessingStatus.PENDING,
}


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
            for cal, row_status, has, _, n in rows
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
        reasons: dict[str, int] = {}
        for cal, row_status, _, reason, n in rows:
            if not cal and row_status == ProcessingStatus.SKIPPED:
                key = reason or "no reason recorded"
                reasons[key] = reasons.get(key, 0) + n
        stages.append(
            EnrichmentStageProgress(
                name="gate",
                label="Gate (GLiNER + mail categories)",
                total=text_total,
                completed=gate_scored,
                skipped=gate_skipped,
                skip_reasons=reasons,
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


def _archive_stages(progress: DatasetEnrichmentProgress, run_progress: dict | None) -> list[EnrichmentStageProgress]:
    """A running unpack: the archives, then the members of the one being unpacked now."""
    current = ((run_progress or {}).get("archives") or {}).get("current")
    if not current:
        return []
    done = current.get("members_done", 0)
    return [
        EnrichmentStageProgress(
            name="archives",
            label="Archives",
            total=progress.total,
            completed=progress.completed,
            skipped=progress.counts.get(ProcessingStatus.SKIPPED, 0),
            failed=progress.counts.get(ProcessingStatus.FAILED, 0),
            skip_reasons=progress.skip_reasons,
        ),
        EnrichmentStageProgress(
            name="members",
            label=f"Members of {current.get('filename', 'the current archive')}",
            total=current.get("members_total") or done,  # a streamed tar's count is unknown until its end
            completed=done,
        ),
    ]


def _from_run(dataset_id: str, enrichment_type: EnrichmentType, run) -> DatasetEnrichmentProgress:
    """Progress of a dataset-wide pass from its latest run: done (with the units it covered), failed, stopped, or running."""
    status = _RUN_STATUS.get(run.status, ProcessingStatus.PROCESSING)
    units = run.unit_count if status == ProcessingStatus.COMPLETED else 1
    progress = _to_progress(dataset_id, enrichment_type, {status: units} if units else {})
    progress.progress = 1.0 if status == ProcessingStatus.COMPLETED else 0.0
    progress.date_last_run = run.date_started
    progress.is_running = status == ProcessingStatus.PROCESSING
    return progress


async def _dataset_progress(
    datastore, run_datastore, dataset_id: str, types: list[EnrichmentType]
) -> list[DatasetEnrichmentProgress]:
    stats = await datastore.get_enrichment_stats(dataset_id=dataset_id)
    reasons = await datastore.get_skip_reasons(dataset_id=dataset_id)
    runs = await run_datastore.latest_for_dataset(dataset_id=dataset_id, enrichment_types=types)
    items = []
    for enrichment_type in types:
        if stats.get(enrichment_type):
            progress = _to_progress(dataset_id, enrichment_type, stats[enrichment_type])
            progress.skip_reasons = reasons.get(enrichment_type, {})
            run = runs.get(enrichment_type)
            progress.is_running = (run is not None and run.status == "running") or bool(
                stats[enrichment_type].get(ProcessingStatus.PROCESSING)
            )
            if enrichment_type == EnrichmentType.EVENT_EXTRACTION:
                progress.stages = await _event_stages(datastore, dataset_id)
            if enrichment_type == EnrichmentType.ARCHIVE_EXTRACTION and progress.is_running and run is not None:
                progress.stages = _archive_stages(progress, run.progress)
            items.append(progress)
        elif enrichment_type in _RUN_TRACKED and (run := runs.get(enrichment_type)):
            items.append(_from_run(dataset_id, enrichment_type, run))
    return items


@router.get(
    "/progress",
    response_model=DatasetEnrichmentProgress,
    response_model_by_alias=True,
)
async def get_enrichment_progress(
    datastore: EnrichmentDatastoreDep,
    run_datastore: EnrichmentRunDatastoreDep,
    enrichment_type: Annotated[EnrichmentType, Query(alias="enrichmentType")],
    dataset_id: DatasetIdQueryDep,
):
    """Get enrichment progress for a given dataset and enrichment type."""
    items = await _dataset_progress(datastore, run_datastore, dataset_id, [enrichment_type])
    return items[0] if items else _to_progress(dataset_id, enrichment_type, {})


@router.get(
    "/progress/all",
    response_model=list[DatasetEnrichmentProgress],
    response_model_by_alias=True,
)
async def get_dataset_enrichment_progress(
    datastore: EnrichmentDatastoreDep, run_datastore: EnrichmentRunDatastoreDep, dataset_id: DatasetIdQueryDep
):
    """Progress for every analytic that has run against `dataset_id`, in pipeline order (others appended)."""
    stats = await datastore.get_enrichment_stats(dataset_id=dataset_id)
    return await _dataset_progress(
        datastore, run_datastore, dataset_id, [*PIPELINE_ORDER, *(t for t in stats if t not in PIPELINE_ORDER)]
    )


@router.get("/resolution", response_model=SweepRun | None, response_model_by_alias=True)
async def get_resolution_run(
    run_datastore: EnrichmentRunDatastoreDep, dataset_id: DatasetIdQueryDep
) -> SweepRun | None:
    """The latest entity-resolution run on a dataset (`cipher resolve-entities`) with each step's progress."""
    run = await run_datastore.latest_run(dataset_id=dataset_id, enrichment_type=RESOLUTION_RUN)
    if run is None:
        return None
    return SweepRun(
        status=run.status,
        date_started=run.date_started,
        date_completed=run.date_completed,
        duration_seconds=run.duration_seconds,
        error_message=run.error_message,
        steps=(run.progress or {}).get("steps", []),
    )


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
