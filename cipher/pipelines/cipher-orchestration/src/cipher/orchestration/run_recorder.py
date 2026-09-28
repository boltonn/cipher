"""Record each enrichment workflow invocation into `enrichment_run`.

Wrap an enrichment command body in `record_run(...)` and set `run.units` to the
count the workflow returns. The row is written on its own session so a workflow
rollback never loses the timing record, and a failing workflow still leaves a
`failed` row (with the error) behind for calibration and audit.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.repositories import PostgresEnrichmentRunRepository
from cipher.orchestration.session import get_async_engine_from_settings


@dataclass
class RunTally:
    """Mutable handle the caller sets `units` on before the block exits."""

    units: int = 0


@asynccontextmanager
async def record_run(
    *,
    enrichment_type: str,
    dataset_id: str | None,
    device: str = "na",
    unit: str = "file",
    params: dict | None = None,
) -> AsyncIterator[RunTally]:
    """Open an `enrichment_run` row, yield a tally, close it terminal on exit."""
    engine = get_async_engine_from_settings()
    tally = RunTally()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        repo = PostgresEnrichmentRunRepository(session=session)
        run_id = await repo.start_run(
            enrichment_type=str(enrichment_type),
            dataset_id=dataset_id,
            device=str(device),
            unit=str(unit),
            params=params or {},
        )
        try:
            yield tally
        except Exception as exc:
            await repo.finish_run(
                run_id, unit_count=tally.units, status="failed", error_message=f"{type(exc).__name__}: {exc}"[:2000]
            )
            raise
        await repo.finish_run(run_id, unit_count=tally.units, status="completed")
        logger.debug(f"enrichment_run {run_id}: {enrichment_type} {tally.units} {unit}(s) on {device}")
