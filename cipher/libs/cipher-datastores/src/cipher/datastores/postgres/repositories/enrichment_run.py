"""Read/write the `enrichment_run` audit + calibration log."""

from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.enrichment_run import EnrichmentRunTable
from cipher.schemas.ingestion.enrichment import EnrichmentType
from cipher.schemas.ingestion.estimation import RateStat, RunDevice


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
        row = EnrichmentRunTable(
            enrichment_type=str(enrichment_type),
            dataset_id=dataset_id,
            device=str(device),
            unit=str(unit),
            params=params or {},
            status="running",
            date_started=datetime.now(UTC),
        )
        self.session.add(row)
        await self.session.commit()
        return row.id

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
        row.unit_count = int(unit_count or 0)
        row.status = status
        row.error_message = error_message
        row.date_completed = now
        row.duration_seconds = (now - started).total_seconds() if started else None
        await self.session.commit()

    async def get_rates(self, *, min_samples: int = 1) -> dict[tuple[EnrichmentType, RunDevice], RateStat]:
        """Median / p25 / p75 seconds-per-unit per (enrichment_type, device).

        Only `completed` runs with a positive unit count contribute. Groups with
        fewer than `min_samples` runs are dropped.
        """
        per_unit = EnrichmentRunTable.duration_seconds / func.nullif(EnrichmentRunTable.unit_count, 0)
        stmt = (
            select(
                EnrichmentRunTable.enrichment_type,
                EnrichmentRunTable.device,
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
            .group_by(EnrichmentRunTable.enrichment_type, EnrichmentRunTable.device)
        )

        rates: dict[tuple[EnrichmentType, RunDevice], RateStat] = {}
        for enrichment_type, device, p50, p25, p75, n in (await self.session.execute(stmt)).all():
            if n < min_samples or p50 is None:
                continue
            try:
                etype = EnrichmentType(enrichment_type)
                rdev = RunDevice(device)
            except ValueError:
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
        stmt = select(EnrichmentRunTable).order_by(EnrichmentRunTable.date_started.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())
