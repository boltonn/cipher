"""Read/write the `enrichment_run` audit + calibration log, and the run-plan steps that live in it."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from loguru import logger
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.enrichment_run import EnrichmentRunTable
from cipher.schemas.ingestion.enrichment import EnrichmentType
from cipher.schemas.ingestion.estimation import RateStat, RunDevice, work_unit
from cipher.schemas.ingestion.run_plan import (
    DATASET_WIDE_STEPS,
    FINISHED,
    HEARTBEAT_TIMEOUT_SECONDS,
    LIVE,
    NOT_STARTED,
    RunStatus,
)

_LIVE = [status.value for status in LIVE]
_NOT_STARTED = [status.value for status in NOT_STARTED]


def _stale_before() -> datetime:
    return datetime.now(UTC) - timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS)


# Serialises claims so service caps and one-per-dataset checks can't race; claims are rare.
_CLAIM_LOCK = "SELECT pg_advisory_xact_lock(hashtext('cipher-run-claim'))"

_CAPS_OK = """
NOT EXISTS (
    SELECT 1 FROM unnest(r.services) AS s(name)
    WHERE (SELECT count(*) FROM enrichment_run x WHERE x.status IN ('running', 'cancelling') AND s.name = ANY(x.services))
        >= COALESCE((CAST(:caps AS jsonb) ->> s.name)::int, 1)
)
AND (:strict = false OR r.code_version -> 'approved' ->> 'sha' IS NULL
     OR r.code_version -> 'approved' ->> 'sha' = :sha)
"""

_NEXT_QUEUED = f"""
SELECT r.id FROM enrichment_run r
WHERE r.status = 'queued' AND r.pool = :pool AND r.dataset_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM unnest(r.depends_on) AS dep(step)
      WHERE NOT EXISTS (SELECT 1 FROM enrichment_run d
                        WHERE d.plan_id = r.plan_id AND d.enrichment_type = dep.step AND d.status = 'completed')
         OR EXISTS (SELECT 1 FROM enrichment_run d
                    WHERE d.plan_id = r.plan_id AND d.enrichment_type = dep.step
                      AND d.status IN ('queued', 'running', 'cancelling'))
  )
  AND NOT (r.enrichment_type = ANY(:dataset_wide) AND EXISTS (
      SELECT 1 FROM enrichment_run x WHERE x.dataset_id = r.dataset_id AND x.enrichment_type = r.enrichment_type
        AND x.status IN ('running', 'cancelling')))
  AND {_CAPS_OK}
ORDER BY r.date_approved, r.position
LIMIT 1
"""

_JOINABLE = f"""
SELECT r.id FROM enrichment_run r
WHERE r.plan_id IS NOT NULL AND r.status = 'running' AND r.pool = :pool AND r.dataset_id IS NOT NULL
  AND NOT (r.enrichment_type = ANY(:dataset_wide))
  AND (SELECT count(*) FROM enrichment_run x WHERE x.plan_id = r.plan_id AND x.enrichment_type = r.enrichment_type
         AND x.status IN ('running', 'cancelling')) < :max_hosts
  AND NOT EXISTS (SELECT 1 FROM enrichment_run x WHERE x.plan_id = r.plan_id AND x.enrichment_type = r.enrichment_type
         AND x.status IN ('running', 'cancelling') AND split_part(x.worker, ':', 1) = :host)
  AND EXISTS (SELECT 1 FROM enrichment e JOIN file f ON f.id = e.enrichable_id
              WHERE e.enrichment_type = upper(r.enrichment_type) AND e.status = 'PENDING' AND f.dataset_id = r.dataset_id)
  AND {_CAPS_OK}
ORDER BY r.date_started
LIMIT 1
"""


class PostgresEnrichmentRunRepository:
    """Postgres implementation for enrichment run records."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def start_run(
        self,
        *,
        enrichment_type: str,
        dataset_id: str | None,
        device: str,
        unit: str,
        params: dict | None = None,
    ) -> str:
        """Insert a `running` row and return its id."""
        now = datetime.now(UTC)
        row = EnrichmentRunTable(
            enrichment_type=str(enrichment_type),
            dataset_id=dataset_id,
            device=str(device),
            unit=str(unit),
            params=params or {},
            status="running",
            date_created=now,
            date_started=now,
            date_heartbeat=now,
        )
        self.session.add(row)
        await self.session.commit()
        return row.id

    async def adopt_run(self, run_id: str, *, enrichment_type: str, device: str, unit: str) -> bool:
        """Take over a plan step a worker claimed for this process, if it is this analytic and still live."""
        result = await self.session.execute(
            update(EnrichmentRunTable)
            .where(
                EnrichmentRunTable.id == run_id,
                EnrichmentRunTable.enrichment_type == str(enrichment_type),
                EnrichmentRunTable.status.in_(_LIVE),
            )
            .values(device=str(device), unit=str(unit), date_heartbeat=datetime.now(UTC))
        )
        await self.session.commit()
        return bool(result.rowcount)

    async def heartbeat(self, run_ids: list[str]) -> dict[str, str]:
        """Stamp `date_heartbeat` on these live runs; returns each one's status (to notice `cancelling`)."""
        if not run_ids:
            return {}
        rows = await self.session.execute(
            update(EnrichmentRunTable)
            .where(EnrichmentRunTable.id.in_(run_ids), EnrichmentRunTable.status.in_(_LIVE))
            .values(date_heartbeat=datetime.now(UTC))
            .returning(EnrichmentRunTable.id, EnrichmentRunTable.status)
        )
        statuses = {run_id: status for run_id, status in rows.all()}
        await self.session.commit()
        return statuses

    async def close_interrupted_runs(self, *, enrichment_type: str | None = None, dataset_id: str | None = None) -> int:
        """Close live rows whose process is gone (no fresh heartbeat); runs still beating are left alone.

        A plan step a worker lost goes back to `queued` for another worker (`cancelled` if it was
        being cancelled); any other row is marked `stopped`.

        Args:
            enrichment_type: Limit to one analytic; all when omitted.
            dataset_id: Limit to one dataset (with `enrichment_type`).
        """
        lost = [
            EnrichmentRunTable.status.in_(_LIVE),
            or_(EnrichmentRunTable.date_heartbeat.is_(None), EnrichmentRunTable.date_heartbeat < _stale_before()),
        ]
        if enrichment_type is not None:
            lost += [
                EnrichmentRunTable.enrichment_type == str(enrichment_type),
                EnrichmentRunTable.dataset_id == dataset_id,
            ]
        closed = 0
        for where, values in (
            (
                [EnrichmentRunTable.plan_id.is_not(None), EnrichmentRunTable.status == RunStatus.RUNNING.value],
                {"status": RunStatus.QUEUED.value, "error_message": "its worker stopped responding; queued again"},
            ),
            (
                [EnrichmentRunTable.plan_id.is_not(None), EnrichmentRunTable.status == RunStatus.CANCELLING.value],
                {"status": RunStatus.CANCELLED.value, "date_completed": datetime.now(UTC)},
            ),
            (
                [EnrichmentRunTable.plan_id.is_(None)],
                {"status": RunStatus.STOPPED.value, "error_message": "process ended without closing the run"},
            ),
        ):
            result = await self.session.execute(update(EnrichmentRunTable).where(*lost, *where).values(**values))
            closed += result.rowcount or 0
        await self.session.commit()
        return closed

    async def finish_run(
        self,
        run_id: str,
        *,
        unit_count: int,
        status: str = "completed",
        error_message: str | None = None,
    ) -> None:
        """Stamp a run terminal: unit count, end time, and derived duration."""
        row = await self.session.get(EnrichmentRunTable, run_id)
        if row is None:
            logger.warning(f"finish_run: no enrichment_run {run_id}")
            return
        now = datetime.now(UTC)
        started = row.date_started
        if started is not None and started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        if row.status == RunStatus.CANCELLING.value and status != RunStatus.COMPLETED.value:
            status = RunStatus.CANCELLED.value
        row.unit_count = int(unit_count or 0)
        row.status = status
        row.error_message = error_message
        row.date_completed = now
        row.duration_seconds = (now - started).total_seconds() if started else None
        await self.session.commit()

    async def get_rates(self, *, min_samples: int = 1) -> dict[tuple[EnrichmentType, RunDevice], RateStat]:
        """Median / p25 / p75 seconds-per-unit per (enrichment_type, device).

        Only `completed` runs with a positive unit count, recorded in the analytic's own
        work unit, contribute. Groups with fewer than `min_samples` runs are dropped.
        """
        per_unit = EnrichmentRunTable.duration_seconds / func.nullif(EnrichmentRunTable.unit_count, 0)
        stmt = (
            select(
                EnrichmentRunTable.enrichment_type,
                EnrichmentRunTable.device,
                EnrichmentRunTable.unit,
                func.percentile_cont(0.5).within_group(per_unit).label("p50"),
                func.percentile_cont(0.25).within_group(per_unit).label("p25"),
                func.percentile_cont(0.75).within_group(per_unit).label("p75"),
                func.count().label("n"),
            )
            .where(
                EnrichmentRunTable.status == "completed",
                EnrichmentRunTable.unit_count > 0,
                EnrichmentRunTable.duration_seconds.is_not(None),
            )
            .group_by(EnrichmentRunTable.enrichment_type, EnrichmentRunTable.device, EnrichmentRunTable.unit)
        )

        rates: dict[tuple[EnrichmentType, RunDevice], RateStat] = {}
        for enrichment_type, device, unit, p50, p25, p75, n in (await self.session.execute(stmt)).all():
            if n < min_samples or p50 is None:
                continue
            try:
                etype = EnrichmentType(enrichment_type)
                rdev = RunDevice(device)
            except ValueError:
                continue
            if unit != work_unit(etype):
                continue
            rates[(etype, rdev)] = RateStat(
                enrichment_type=etype,
                device=rdev,
                seconds_per_unit=float(p50),
                low_per_unit=float(p25 if p25 is not None else p50),
                high_per_unit=float(p75 if p75 is not None else p50),
                sample_size=int(n),
            )
        return rates

    async def list_recent(self, *, limit: int = 50) -> list[EnrichmentRunTable]:
        """Most recent runs first -- for `cipher rates` / an ops view."""
        stmt = (
            select(EnrichmentRunTable)
            .where(EnrichmentRunTable.status.not_in(_NOT_STARTED))
            .order_by(EnrichmentRunTable.date_started.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def latest_for_dataset(
        self, *, dataset_id: str, enrichment_types: list[EnrichmentType]
    ) -> dict[EnrichmentType, EnrichmentRunTable]:
        """The most recent run of each of these analytics against a dataset."""
        stmt = (
            select(EnrichmentRunTable)
            .where(
                EnrichmentRunTable.dataset_id == dataset_id,
                EnrichmentRunTable.enrichment_type.in_([t.value for t in enrichment_types]),
                EnrichmentRunTable.status.not_in(_NOT_STARTED),
            )
            .order_by(EnrichmentRunTable.enrichment_type, EnrichmentRunTable.date_started.desc())
            .distinct(EnrichmentRunTable.enrichment_type)
        )
        return {EnrichmentType(row.enrichment_type): row for row in (await self.session.execute(stmt)).scalars()}

    async def set_progress(self, run_id: str, progress: dict) -> None:
        """Replace a running run's per-step progress."""
        row = await self.session.get(EnrichmentRunTable, run_id)
        if row is not None:
            row.progress = progress
            await self.session.commit()

    async def latest_run(
        self, *, dataset_id: str, enrichment_type: str, status: str | None = None
    ) -> EnrichmentRunTable | None:
        """The most recent run of one analytic (or sweep) on a dataset, optionally only with this status."""
        stmt = select(EnrichmentRunTable).where(
            EnrichmentRunTable.dataset_id == dataset_id,
            EnrichmentRunTable.enrichment_type == enrichment_type,
            EnrichmentRunTable.status.not_in(_NOT_STARTED),
        )
        if status:
            stmt = stmt.where(EnrichmentRunTable.status == status)
        return (await self.session.execute(stmt.order_by(EnrichmentRunTable.date_started.desc()).limit(1))).scalar()

    # -- run plans -------------------------------------------------------------------------

    async def create_plan(
        self,
        *,
        dataset_id: str,
        steps: list[dict],
        note: str | None,
        queued_by: str,
        approved_on: dict,
    ) -> str:
        """Queue one row per step, all sharing a new `plan_id`.

        Args:
            dataset_id: The dataset.
            steps: Per step: `step_type`, `parameters`, `pool`, `services`, `depends_on`, `position`.
            note: Why.
            queued_by: The admin who queued it.
            approved_on: Code version it was queued on.
        """
        plan_id = str(uuid4())
        now = datetime.now(UTC)
        for step in steps:
            self.session.add(
                EnrichmentRunTable(
                    plan_id=plan_id,
                    enrichment_type=step["step_type"],
                    dataset_id=dataset_id,
                    params=step["parameters"],
                    pool=step["pool"],
                    services=step["services"],
                    depends_on=step["depends_on"],
                    position=step["position"],
                    status=RunStatus.QUEUED.value,
                    note=note,
                    requested_by=queued_by,
                    approved_by=queued_by,
                    date_approved=now,
                    code_version={"approved": approved_on},
                    date_created=now,
                    date_started=now,
                )
            )
        await self.session.commit()
        return plan_id

    async def plan_rows(self, plan_id: str) -> list[EnrichmentRunTable]:
        """Every row of one plan, in step order (re-runs after the row they repeat)."""
        rows = await self.session.execute(
            select(EnrichmentRunTable)
            .where(EnrichmentRunTable.plan_id == plan_id)
            .order_by(EnrichmentRunTable.position, EnrichmentRunTable.date_created)
        )
        return list(rows.scalars())

    async def list_plan_rows(
        self,
        *,
        dataset_ids: list[str] | None = None,
        statuses: list[RunStatus] | None = None,
        limit: int = 50,
    ) -> list[EnrichmentRunTable]:
        """Rows of the most recent plans matching the filters (whole plans, never partial).

        Args:
            dataset_ids: Plans on these datasets (`None` = any).
            statuses: Plans with at least one row in one of these statuses.
            limit: Most plans returned.
        """
        conditions = [EnrichmentRunTable.plan_id.is_not(None)]
        if dataset_ids is not None:
            conditions.append(EnrichmentRunTable.dataset_id.in_(dataset_ids))
        if statuses:
            conditions.append(EnrichmentRunTable.status.in_([status.value for status in statuses]))
        latest = (
            select(EnrichmentRunTable.plan_id, func.max(EnrichmentRunTable.date_created).label("date_created"))
            .where(*conditions)
            .group_by(EnrichmentRunTable.plan_id)
            .order_by(func.max(EnrichmentRunTable.date_created).desc())
            .limit(limit)
            .subquery()
        )
        rows = await self.session.execute(
            select(EnrichmentRunTable)
            .join(latest, latest.c.plan_id == EnrichmentRunTable.plan_id)
            .order_by(
                latest.c.date_created.desc(),
                EnrichmentRunTable.plan_id,
                EnrichmentRunTable.position,
                EnrichmentRunTable.date_created,
            )
        )
        return list(rows.scalars())

    async def cancel(self, *, plan_id: str | None = None, run_id: str | None = None) -> int:
        """Cancel a plan or one step: waiting rows end `cancelled`, running ones go `cancelling` for their worker."""
        scope = EnrichmentRunTable.plan_id == plan_id if plan_id else EnrichmentRunTable.id == run_id
        now = datetime.now(UTC)
        waiting = await self.session.execute(
            update(EnrichmentRunTable)
            .where(scope, EnrichmentRunTable.status.in_(_NOT_STARTED))
            .values(status=RunStatus.CANCELLED.value, date_completed=now)
        )
        running = await self.session.execute(
            update(EnrichmentRunTable)
            .where(scope, EnrichmentRunTable.status == RunStatus.RUNNING.value)
            .values(status=RunStatus.CANCELLING.value)
        )
        dependents = await self._cancel_dependents(run_id) if run_id else 0
        await self.session.commit()
        return (waiting.rowcount or 0) + (running.rowcount or 0) + dependents

    async def _cancel_dependents(self, run_id: str) -> int:
        """Cancel the queued steps of the same plan that wait (directly or not) on this step: they could never start."""
        row = await self.session.get(EnrichmentRunTable, run_id)
        if row is None or row.plan_id is None:
            return 0
        blocked, frontier, cancelled = {row.enrichment_type}, [row.enrichment_type], 0
        while frontier:
            step_type = frontier.pop()
            result = await self.session.execute(
                update(EnrichmentRunTable)
                .where(
                    EnrichmentRunTable.plan_id == row.plan_id,
                    EnrichmentRunTable.status == RunStatus.QUEUED.value,
                    EnrichmentRunTable.depends_on.any(step_type),
                )
                .values(status=RunStatus.CANCELLED.value, date_completed=datetime.now(UTC))
                .returning(EnrichmentRunTable.enrichment_type)
            )
            for (dependent,) in result.all():
                cancelled += 1
                if dependent not in blocked:
                    blocked.add(dependent)
                    frontier.append(dependent)
        return cancelled

    async def requeue(self, run_id: str, *, queued_by: str, approved_on: dict) -> bool:
        """Queue a finished step again in place (its undone files are still pending)."""
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(EnrichmentRunTable)
            .where(
                EnrichmentRunTable.id == run_id,
                EnrichmentRunTable.plan_id.is_not(None),
                EnrichmentRunTable.status.in_([status.value for status in FINISHED]),
            )
            .values(
                status=RunStatus.QUEUED.value,
                worker=None,
                process=None,
                error_message=None,
                progress=None,
                unit_count=0,
                duration_seconds=None,
                date_completed=None,
                date_heartbeat=None,
                date_created=now,
                date_started=now,
                approved_by=queued_by,
                date_approved=now,
                code_version={"approved": approved_on},
            )
        )
        await self.session.commit()
        return bool(result.rowcount)

    async def claim_next(
        self,
        *,
        pool: str,
        worker: str,
        caps: dict[str, int],
        ran_on: dict,
        is_strict_version: bool = False,
        max_hosts_per_step: int = 4,
    ) -> EnrichmentRunTable | None:
        """Claim the next runnable step for this pool, else join a running per-file step that still has work.

        Lost runs (no fresh heartbeat) are recovered first. Dependencies, service caps and
        one-at-a-time-per-dataset steps are checked under one advisory lock.

        Args:
            pool: `cpu` or `gpu`.
            worker: `host:pid` of the claimer.
            caps: Most steps per service at once (missing services cap at 1).
            ran_on: This host's code version.
            is_strict_version: Refuse steps approved on another commit.
            max_hosts_per_step: Most hosts sharing one per-file step.
        """
        await self.close_interrupted_runs()
        await self.session.execute(text(_CLAIM_LOCK))
        params = {
            "pool": pool,
            "caps": json.dumps(caps),
            "strict": is_strict_version,
            "sha": ran_on.get("sha"),
            "dataset_wide": sorted(DATASET_WIDE_STEPS),
        }
        now = datetime.now(UTC)
        run_id = (await self.session.execute(text(_NEXT_QUEUED), params)).scalar()
        if run_id is not None:
            row = await self.session.get(EnrichmentRunTable, run_id)
            row.status = RunStatus.RUNNING.value
            row.worker = worker
            row.date_started = now
            row.date_heartbeat = now
            row.error_message = None
            row.code_version = {**(row.code_version or {}), "ran": ran_on}
            await self.session.commit()
            return row
        host = worker.split(":", 1)[0]
        joined_id = (
            await self.session.execute(text(_JOINABLE), {**params, "host": host, "max_hosts": max_hosts_per_step})
        ).scalar()
        if joined_id is None:
            await self.session.commit()
            return None
        source = await self.session.get(EnrichmentRunTable, joined_id)
        row = EnrichmentRunTable(
            plan_id=source.plan_id,
            enrichment_type=source.enrichment_type,
            dataset_id=source.dataset_id,
            params=source.params,
            pool=source.pool,
            services=source.services,
            depends_on=source.depends_on,
            position=source.position,
            status=RunStatus.RUNNING.value,
            note=source.note,
            requested_by=source.requested_by,
            approved_by=source.approved_by,
            date_approved=source.date_approved,
            code_version={"approved": (source.code_version or {}).get("approved"), "ran": ran_on},
            worker=worker,
            date_created=now,
            date_started=now,
            date_heartbeat=now,
        )
        self.session.add(row)
        await self.session.commit()
        return row

    async def set_process(self, run_id: str, process: dict) -> None:
        """Record where a step's process runs: `{host, worker_pid, pid, log}`."""
        await self.session.execute(
            update(EnrichmentRunTable).where(EnrichmentRunTable.id == run_id).values(process=process)
        )
        await self.session.commit()

    async def live_steps(self, *, host: str | None = None) -> list[EnrichmentRunTable]:
        """Plan steps queued or running, oldest first; `host` limits to steps running there."""
        stmt = select(EnrichmentRunTable).where(
            EnrichmentRunTable.plan_id.is_not(None),
            EnrichmentRunTable.status.in_([RunStatus.QUEUED.value, *_LIVE]),
        )
        if host:
            stmt = stmt.where(EnrichmentRunTable.process["host"].astext == host)
        return list((await self.session.execute(stmt.order_by(EnrichmentRunTable.date_created))).scalars())

    async def finish_step(self, run_id: str, *, exit_code: int, error_message: str | None) -> None:
        """Close a step its command left open (commands without `record_run`, or a crash), from the exit code."""
        row = await self.session.get(EnrichmentRunTable, run_id)
        if row is None or row.status not in _LIVE:
            return
        if row.status == RunStatus.CANCELLING.value:
            status = RunStatus.CANCELLED.value
        else:
            status = RunStatus.COMPLETED.value if exit_code == 0 else RunStatus.FAILED.value
        await self.finish_run(
            run_id, unit_count=row.unit_count, status=status, error_message=None if exit_code == 0 else error_message
        )
