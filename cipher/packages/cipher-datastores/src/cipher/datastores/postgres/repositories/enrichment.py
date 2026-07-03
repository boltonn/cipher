from collections import defaultdict
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.enrichment import EnrichmentTable
from cipher.datastores.postgres.tables.face import FaceTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.message import MessageTable
from cipher.schemas.enrichment import (
    EnrichableType,
    Enrichment,
    EnrichmentBatchItem,
    EnrichmentType,
    ProcessingStatus,
)


class PostgresEnrichmentRepository:
    """Repository for polymorphic enrichment queue operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the enrichment table."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(EnrichmentTable.metadata.create_all)

    async def queue_enrichments_for_resource(
        self,
        enrichable_type: EnrichableType,
        enrichable_id: str,
        enrichment_types: list[EnrichmentType],
    ) -> list[Enrichment]:
        """Queue enrichments for a resource."""
        enrichments = []

        for enrichment_type in enrichment_types:
            result = await self.session.execute(
                select(EnrichmentTable).where(
                    EnrichmentTable.enrichable_type == enrichable_type,
                    EnrichmentTable.enrichable_id == enrichable_id,
                    EnrichmentTable.enrichment_type == enrichment_type,
                )
            )
            existing = result.scalar_one_or_none()

            if not existing:
                enrichment = EnrichmentTable(
                    enrichable_type=enrichable_type,
                    enrichable_id=enrichable_id,
                    enrichment_type=enrichment_type,
                    status=ProcessingStatus.PENDING,
                )
                self.session.add(enrichment)
                enrichments.append(Enrichment.model_validate(enrichment))
            else:
                enrichments.append(Enrichment.model_validate(existing))

        await self.session.commit()
        return enrichments

    async def get_pending_batch(
        self,
        enrichment_type: EnrichmentType,
        enrichable_type: EnrichableType,
        batch_size: int = 100,
        dataset_id: str | None = None,
        max_retries: int = 3,
        filetype_group_filter: str | None = None,
        filetype_filter: str | None = None,
    ) -> list[EnrichmentBatchItem]:
        """Get a batch of enrichments using SELECT FOR UPDATE SKIP LOCKED."""
        # Map enrichable type to the appropriate table
        resource_table_map = {
            EnrichableType.FILE: FileTable,
            EnrichableType.MESSAGE: MessageTable,
            EnrichableType.FACE: FaceTable,
        }

        resource_table = resource_table_map.get(enrichable_type)
        if not resource_table:
            return []

        statement = (
            select(EnrichmentTable, resource_table)
            .join(resource_table, EnrichmentTable.enrichable_id == resource_table.id)
            .where(
                EnrichmentTable.enrichable_type == enrichable_type,
                EnrichmentTable.enrichment_type == enrichment_type,
            )
            .where(
                or_(
                    EnrichmentTable.status == ProcessingStatus.PENDING,
                    (EnrichmentTable.status == ProcessingStatus.FAILED) & (EnrichmentTable.retry_count < max_retries),
                )
            )
            .order_by(EnrichmentTable.date_created)
            .limit(batch_size)
            .with_for_update(of=EnrichmentTable, skip_locked=True)
        )

        # Add filters based on enrichable type
        if enrichable_type == EnrichableType.FILE:
            if dataset_id:
                statement = statement.where(FileTable.dataset_id == dataset_id)
            if filetype_filter:
                statement = statement.where(FileTable.filetype == filetype_filter)
            elif filetype_group_filter:
                statement = statement.where(FileTable.filetype_group == filetype_group_filter)

        result = await self.session.execute(statement)
        rows = list(result.all())

        return [
            EnrichmentBatchItem(
                enrichment=Enrichment.model_validate(enrichment),
                resource=resource.__dict__,
            )
            for enrichment, resource in rows
        ]

    async def mark_processing(self, enrichment_ids: list[str]) -> None:
        """Mark enrichments as PROCESSING."""
        statement = (
            update(EnrichmentTable)
            .where(EnrichmentTable.id.in_(enrichment_ids))
            .values(
                status=ProcessingStatus.PROCESSING,
                date_started=datetime.now(UTC),
                date_updated=datetime.now(UTC),
            )
        )
        await self.session.execute(statement)

    async def mark_completed_batch(self, enrichment_ids: list[str]) -> None:
        """Mark enrichment as COMPLETED."""
        statement = (
            update(EnrichmentTable)
            .where(EnrichmentTable.id.in_(enrichment_ids))
            .values(
                status=ProcessingStatus.COMPLETED,
                date_completed=datetime.now(UTC),
                date_updated=datetime.now(UTC),
            )
        )
        await self.session.execute(statement)

    async def mark_failed_batch(
        self,
        enrichment_ids: list[str],
        error_message: str | None = None,
        increment_retry: bool = True,
    ) -> None:
        """Mark enrichment as FAILED."""
        if not enrichment_ids:
            return

        values = {
            "status": ProcessingStatus.FAILED,
            "date_updated": datetime.now(UTC),
        }

        if error_message:
            values["error_message"] = error_message

        if increment_retry:
            values["retry_count"] = EnrichmentTable.retry_count + 1

        await self.session.execute(
            update(EnrichmentTable).where(EnrichmentTable.id.in_(enrichment_ids)).values(**values)
        )

    async def reset_stuck_enrichments(self, stuck_threshold_minutes: int = 60) -> int:
        """Reset stuck enrichments and return row count."""
        threshold = datetime.now(UTC) - timedelta(minutes=stuck_threshold_minutes)
        statement = (
            update(EnrichmentTable)
            .where(
                EnrichmentTable.status == ProcessingStatus.PROCESSING,
                EnrichmentTable.date_started < threshold,
            )
            .values(
                status=ProcessingStatus.PENDING,
                date_started=None,
                date_updated=datetime.now(UTC),
            )
        )
        result = await self.session.execute(statement)
        await self.session.commit()
        return result.rowcount or 0

    async def get_enrichment_stats(
        self,
        enrichable_type: EnrichableType | None = None,
        dataset_id: str | None = None,
        enrichment_type: EnrichmentType | None = None,
    ) -> dict[EnrichmentType, dict[ProcessingStatus, int]]:
        """Get statistics grouped by enrichment type and status."""
        statement = select(
            EnrichmentTable.enrichment_type,
            EnrichmentTable.status,
            func.count(EnrichmentTable.id),
        ).group_by(EnrichmentTable.enrichment_type, EnrichmentTable.status)

        if enrichable_type:
            statement = statement.where(EnrichmentTable.enrichable_type == enrichable_type)

        if enrichment_type:
            statement = statement.where(EnrichmentTable.enrichment_type == enrichment_type)

        if dataset_id:
            statement = statement.join(
                FileTable,
                (EnrichmentTable.enrichable_id == FileTable.id)
                & (EnrichmentTable.enrichable_type == EnrichableType.FILE),
            ).where(FileTable.dataset_id == dataset_id)

        result = await self.session.execute(statement)

        stats: dict[EnrichmentType, dict[ProcessingStatus, int]] = defaultdict(lambda: defaultdict(int))
        for enrich_type, status, count in result.all():
            stats[EnrichmentType(enrich_type)][ProcessingStatus(status)] = count
        return dict(stats)

    async def retry_failed_enrichments(
        self,
        enrichment_ids: list[str] | None = None,
        enrichment_type: EnrichmentType | None = None,
        enrichable_type: EnrichableType | None = None,
        dataset_id: str | None = None,
    ) -> int:
        """Reset failed enrichments back to pending."""
        statement = update(EnrichmentTable).where(EnrichmentTable.status == ProcessingStatus.FAILED)

        if enrichment_ids:
            statement = statement.where(EnrichmentTable.id.in_(enrichment_ids))

        if enrichment_type:
            statement = statement.where(EnrichmentTable.enrichment_type == enrichment_type)

        if enrichable_type:
            statement = statement.where(EnrichmentTable.enrichable_type == enrichable_type)

        if dataset_id:
            subquery = select(FileTable.id).where(FileTable.dataset_id == dataset_id)
            statement = statement.where(
                EnrichmentTable.enrichable_type == EnrichableType.FILE,
                EnrichmentTable.enrichable_id.in_(subquery),
            )

        result = await self.session.execute(
            statement.values(
                status=ProcessingStatus.PENDING,
                error_message=None,
                date_started=None,
                date_updated=datetime.now(UTC),
            )
        )
        await self.session.commit()
        return result.rowcount or 0

    async def delete_enrichments(self, enrichment_ids: list[str]) -> int:
        """Delete enrichments."""
        statement = delete(EnrichmentTable).where(EnrichmentTable.id.in_(enrichment_ids))
        result = await self.session.execute(statement)
        await self.session.commit()
        return result.rowcount or 0

    async def count_pending(
        self,
        enrichment_type: EnrichmentType | None = None,
        enrichable_type: EnrichableType | None = None,
        dataset_id: str | None = None,
    ) -> int:
        """Count pending enrichments."""
        statement = select(func.count(EnrichmentTable.id)).where(EnrichmentTable.status == ProcessingStatus.PENDING)

        if enrichment_type:
            statement = statement.where(EnrichmentTable.enrichment_type == enrichment_type)

        if enrichable_type:
            statement = statement.where(EnrichmentTable.enrichable_type == enrichable_type)

        if dataset_id:
            statement = statement.join(
                FileTable,
                (EnrichmentTable.enrichable_id == FileTable.id)
                & (EnrichmentTable.enrichable_type == EnrichableType.FILE),
            ).where(FileTable.dataset_id == dataset_id)

        result = await self.session.execute(statement)
        return result.scalar_one()

    async def queue_enrichments_by_filter(
        self,
        dataset_id: str,
        enrichment_type: EnrichmentType,
        filetype_group: str | None = None,
    ) -> int:
        """Queue enrichments for files matching criteria."""
        # Find files without this enrichment
        query = (
            select(FileTable)
            .outerjoin(
                EnrichmentTable,
                (EnrichmentTable.enrichable_id == FileTable.id)
                & (EnrichmentTable.enrichable_type == EnrichableType.FILE)
                & (EnrichmentTable.enrichment_type == enrichment_type),
            )
            .where(
                EnrichmentTable.id.is_(None),  # No enrichment exists
                FileTable.dataset_id == dataset_id,
            )
        )

        if filetype_group:
            query = query.where(FileTable.filetype_group == filetype_group)

        result = await self.session.execute(query)
        files = list(result.scalars().all())

        # Create enrichments
        count = 0
        for file in files:
            enrichment = EnrichmentTable(
                enrichable_type=EnrichableType.FILE,
                enrichable_id=file.id,
                enrichment_type=enrichment_type,
                status=ProcessingStatus.PENDING,
            )
            self.session.add(enrichment)
            count += 1

        await self.session.flush()
        logger.info(f"Queued {count} {enrichment_type.value} enrichments")
        return count
