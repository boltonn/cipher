"""Record each enrichment workflow invocation into `enrichment_run`.

Before the run starts, PROCESSING claims orphaned by an interrupted run of the
same analytic + dataset are returned to PENDING so this run picks them up.

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

from cipher.datastores.postgres.repositories import PostgresEnrichmentRepository, PostgresEnrichmentRunRepository
from cipher.orchestration.session import get_async_engine_from_settings
from cipher.schemas.ingestion.enrichment import EnrichmentType


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
    """Reset orphaned claims, open an `enrichment_run` row, yield a tally, close it terminal on exit."""
    engine = get_async_engine_from_settings()
    tally = RunTally()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        reset_count = await PostgresEnrichmentRepository(session=session).reset_stuck_enrichments(
            enrichment_type=EnrichmentType(enrichment_type), dataset_id=dataset_id
        )
        if reset_count:
            logger.info(f"Reset {reset_count} orphaned {enrichment_type} claim(s) from an interrupted run to pending")
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
