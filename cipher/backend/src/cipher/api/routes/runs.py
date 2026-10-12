"""Run plans: steps an admin queues for `cipher worker` (docs/pipeline-runner.md).

Anyone with access to a dataset sees its plans (the pipeline shows queued / running / done);
only admins queue, cancel or re-run. Users ask for work through GitHub issues
(`POST /datasets/requests…`). Who queued it comes from the session.
"""

import shlex
from itertools import groupby

from fastapi import APIRouter, HTTPException, Query, status

from cipher.api.deps.access import DatasetAccessDep
from cipher.api.deps.authentication import AdminUserDep
from cipher.api.deps.postgres import DatasetDatastoreDep, EnrichmentRunDatastoreDep, UserDatastoreDep
from cipher.schemas.ingestion.run_plan import (
    CodeVersion,
    PlanRun,
    PlanStep,
    RunPlan,
    RunPlanCreate,
    RunStatus,
    StepProcess,
    plan_order,
    plan_status,
    step_command,
    step_dependencies,
    step_requirements,
)
from cipher.utils.version import code_version

router = APIRouter(prefix="/runs", tags=["runs"])


def _plan_steps(steps: list[PlanStep]) -> list[dict]:
    """Steps in pipeline order with their pool, services and the planned steps each waits for."""
    planned = {step.step_type for step in steps}
    rows = []
    for position, step in enumerate(sorted(steps, key=lambda step: plan_order(step.step_type))):
        requirements = step_requirements(step.step_type, step.parameters)
        rows.append(
            {
                "step_type": step.step_type,
                "parameters": step.parameters,
                "pool": requirements.pool.value,
                "services": [service.value for service in requirements.services],
                "depends_on": step_dependencies(step.step_type, planned),
                "position": position,
            }
        )
    return rows


def _to_run(row) -> PlanRun:
    versions = row.code_version or {}
    ran = versions.get("ran")
    approved_sha = (versions.get("approved") or {}).get("sha")
    is_waiting = row.status == RunStatus.QUEUED
    return PlanRun(
        id=row.id,
        step_type=row.enrichment_type,
        command=shlex.join(["cipher", *step_command(row.enrichment_type, row.params, dataset_id=row.dataset_id)]),
        status=RunStatus(row.status),
        position=row.position,
        pool=row.pool or "cpu",
        services=row.services or [],
        depends_on=row.depends_on or [],
        parameters=row.params or {},
        worker=row.worker,
        process=StepProcess(**row.process) if row.process else None,
        unit=row.unit,
        unit_count=row.unit_count,
        progress=row.progress,
        error_message=row.error_message,
        date_heartbeat=row.date_heartbeat,
        date_started=None if is_waiting else row.date_started,
        date_completed=row.date_completed,
        duration_seconds=row.duration_seconds,
        ran_on=CodeVersion(**ran) if ran else None,
        is_version_mismatch=bool(ran and approved_sha and ran.get("sha") != approved_sha),
    )


async def _to_plans(rows, *, users: UserDatastoreDep) -> list[RunPlan]:
    names: dict[str, str | None] = {}
    plans = []
    for plan_id, group in groupby(rows, key=lambda row: row.plan_id):
        steps = list(group)
        first = steps[0]
        if first.requested_by and first.requested_by not in names:
            user = await users.get_by_id(first.requested_by)
            names[first.requested_by] = user.name if user else None
        approved = (first.code_version or {}).get("approved")
        plans.append(
            RunPlan(
                plan_id=plan_id,
                dataset_id=first.dataset_id,
                status=plan_status([RunStatus(step.status) for step in steps]),
                note=first.note,
                queued_by_name=names.get(first.requested_by) if first.requested_by else None,
                approved_on=CodeVersion(**approved) if approved else None,
                date_created=min(step.date_created for step in steps),
                date_approved=first.date_approved,
                steps=[_to_run(step) for step in steps],
            )
        )
    return plans


@router.post("/plans", summary="Admin: queue steps on a dataset", response_model=RunPlan)
async def create_plan(
    plan: RunPlanCreate,
    admin: AdminUserDep,
    runs: EnrichmentRunDatastoreDep,
    datasets: DatasetDatastoreDep,
    users: UserDatastoreDep,
) -> RunPlan:
    """Queue the steps for the workers, in pipeline order, each waiting for the planned steps it needs."""
    if await datasets.get_dataset_by_id(dataset_id=plan.dataset_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset not found: {plan.dataset_id}")
    plan_id = await runs.create_plan(
        dataset_id=plan.dataset_id,
        steps=_plan_steps(plan.steps),
        note=plan.note,
        queued_by=admin.id,
        approved_on=code_version(),
    )
    return (await _to_plans(await runs.plan_rows(plan_id), users=users))[0]


@router.get("/plans", summary="Recent plans on a dataset", response_model=list[RunPlan])
async def list_plans(
    access: DatasetAccessDep,
    runs: EnrichmentRunDatastoreDep,
    users: UserDatastoreDep,
    dataset_id: str = Query(alias="datasetId"),
    plan_status_filter: list[RunStatus] | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=200),
) -> list[RunPlan]:
    """Newest first: what is queued, running, or recently finished on the dataset."""
    access.require(dataset_id)
    rows = await runs.list_plan_rows(dataset_ids=[dataset_id], statuses=plan_status_filter, limit=limit)
    return await _to_plans(rows, users=users)


@router.post("/plans/{plan_id}/cancel", summary="Admin: cancel a plan", status_code=204)
async def cancel_plan(plan_id: str, admin: AdminUserDep, runs: EnrichmentRunDatastoreDep) -> None:
    """Queued steps end `cancelled`; running ones are stopped by their worker (files done so far are kept)."""
    if not await runs.cancel(plan_id=plan_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nothing in that plan is queued or running")


@router.post("/{run_id}/cancel", summary="Admin: cancel or stop one step", status_code=204)
async def cancel_run(run_id: str, admin: AdminUserDep, runs: EnrichmentRunDatastoreDep) -> None:
    if not await runs.cancel(run_id=run_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That step isn't queued or running")


@router.post("/{run_id}/requeue", summary="Admin: run a finished step again", status_code=204)
async def requeue_run(run_id: str, admin: AdminUserDep, runs: EnrichmentRunDatastoreDep) -> None:
    """Queue it again in place; its undone files are still pending."""
    if not await runs.requeue(run_id, queued_by=admin.id, approved_on=code_version()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a finished step can run again")
