"""Record each enrichment workflow invocation into `enrichment_run`.

Before the run starts, PROCESSING claims left by a run that is no longer alive (no fresh
heartbeat) are returned to PENDING so this run picks them up, and such runs' rows are
closed. Runs still beating -- another host or terminal on the same step -- keep theirs.

While the block runs, its row's `date_heartbeat` is stamped every `HEARTBEAT_SECONDS`, and
every claim made through `mark_processing` records this run's id (`enrichment.run_id`).

Launched by `cipher worker`, a command finds its plan step in `CIPHER_RUN_ID` and records
into that row instead of opening a new one.

A workflow that halts on purpose (e.g. its model server went away) raises
`RunStoppedError` after returning its claims to the queue: the run is recorded
`stopped`, not `failed` -- nothing about the files themselves went wrong. Ctrl-C or
SIGTERM also closes the row `stopped` (`cancelled` when it was being cancelled).

Wrap an enrichment command body in `record_run(...)` and set `run.units` to the
count the workflow returns. The row is written on its own session so a workflow
rollback never loses the timing record, and a failing workflow still leaves a
`failed` row (with the error) behind for calibration and audit.
"""

import asyncio
import os
import signal
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from cipher.datastores.postgres.repositories import PostgresEnrichmentRepository, PostgresEnrichmentRunRepository
from cipher.datastores.postgres.repositories.enrichment import claiming_run_id
from cipher.orchestration.session import get_async_engine_from_settings
from cipher.schemas.ingestion.enrichment import EnrichmentType
from cipher.schemas.ingestion.run_plan import HEARTBEAT_SECONDS

RUN_ID_ENV = "CIPHER_RUN_ID"
GPU_ENV = "CIPHER_GPU"
"""The physical GPU a worker gave this step (for steps that start their own model server)."""


class RunStoppedError(RuntimeError):
    """A run halted before draining its queue; the unprocessed files are back in it for the next run."""


@dataclass
class RunTally:
    """Mutable handle the caller sets `units` on before the block exits (`run_id` for live progress)."""

    units: int = 0
    run_id: str | None = None


def progress_writer(run_id: str) -> Callable[[dict], Awaitable[None]]:
    """An async callback replacing a run's `progress` (each write on its own session)."""
    engine = get_async_engine_from_settings()

    async def write(progress: dict) -> None:
        async with AsyncSession(engine) as session:
            await PostgresEnrichmentRunRepository(session=session).set_progress(run_id, progress)

    return write


@asynccontextmanager
async def keep_alive(engine: AsyncEngine, run_id: str) -> AsyncIterator[None]:
    """Stamp a run's heartbeat in the background, and turn SIGTERM into a cancellation of this task."""

    async def beat() -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            try:
                async with AsyncSession(engine) as session:
                    await PostgresEnrichmentRunRepository(session=session).heartbeat([run_id])
            except Exception as exc:  # a missed beat is retried on the next tick
                logger.warning(f"Heartbeat for run {run_id} failed: {exc}")

    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    handles_sigterm = threading.current_thread() is threading.main_thread() and task is not None
    if handles_sigterm:
        loop.add_signal_handler(signal.SIGTERM, task.cancel)
    beater = asyncio.create_task(beat())
    try:
        yield
    finally:
        beater.cancel()
        with suppress(asyncio.CancelledError):
            await beater
        if handles_sigterm:
            loop.remove_signal_handler(signal.SIGTERM)


@asynccontextmanager
async def record_run(
    *,
    enrichment_type: str,
    dataset_id: str | None,
    device: str = "na",
    unit: str = "file",
    params: dict | None = None,
) -> AsyncIterator[RunTally]:
    """Reset orphaned claims, open (or adopt) an `enrichment_run` row, yield a tally, close it terminal on exit."""
    engine = get_async_engine_from_settings()
    tally = RunTally()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        reset_count = 0
        if enrichment_type in EnrichmentType._value2member_map_:  # steps like staging claim no files
            reset_count = await PostgresEnrichmentRepository(session=session).reset_stuck_enrichments(
                enrichment_type=EnrichmentType(enrichment_type), dataset_id=dataset_id
            )
        if reset_count:
            logger.info(f"Reset {reset_count} orphaned {enrichment_type} claim(s) from an interrupted run to pending")
        repo = PostgresEnrichmentRunRepository(session=session)
        await repo.close_interrupted_runs(enrichment_type=str(enrichment_type), dataset_id=dataset_id)
        planned_id = os.environ.get(RUN_ID_ENV)
        if planned_id and await repo.adopt_run(
            planned_id, enrichment_type=str(enrichment_type), device=str(device), unit=str(unit)
        ):
            run_id = planned_id
        else:
            run_id = await repo.start_run(
                enrichment_type=str(enrichment_type),
                dataset_id=dataset_id,
                device=str(device),
                unit=str(unit),
                params=params or {},
            )
        tally.run_id = run_id
        token = claiming_run_id.set(run_id)
        try:
            async with keep_alive(engine, run_id):
                yield tally
        except RunStoppedError as exc:
            await repo.finish_run(run_id, unit_count=tally.units, status="stopped", error_message=str(exc)[:2000])
            raise
        except (asyncio.CancelledError, KeyboardInterrupt):
            await repo.finish_run(run_id, unit_count=tally.units, status="stopped", error_message="interrupted")
            raise
        except Exception as exc:
            await repo.finish_run(
                run_id, unit_count=tally.units, status="failed", error_message=f"{type(exc).__name__}: {exc}"[:2000]
            )
            raise
        finally:
            claiming_run_id.reset(token)
        await repo.finish_run(run_id, unit_count=tally.units, status="completed")
        logger.debug(f"enrichment_run {run_id}: {enrichment_type} {tally.units} {unit}(s) on {device}")
