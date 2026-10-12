from collections import defaultdict
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import and_, case, delete, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.enrichment import EnrichmentTable
from cipher.datastores.postgres.tables.enrichment_run import EnrichmentRunTable
from cipher.datastores.postgres.tables.face import FaceTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.message import MessageTable
from cipher.schemas.ingestion.enrichment import (
    EnrichableType,
    Enrichment,
    EnrichmentBatchItem,
    EnrichmentType,
    ProcessingStatus,
)
from cipher.schemas.ingestion.run_plan import HEARTBEAT_TIMEOUT_SECONDS, LIVE

claiming_run_id: ContextVar[str | None] = ContextVar("claiming_run_id", default=None)
"""The `enrichment_run` this process is recording; `mark_processing` stamps it on each claim."""


def live_run_ids():
    """Ids of runs whose process is still alive (running, with a fresh heartbeat)."""
    fresh = datetime.now(UTC) - timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS)
    return select(EnrichmentRunTable.id).where(
        EnrichmentRunTable.status.in_([status.value for status in LIVE]), EnrichmentRunTable.date_heartbeat >= fresh
    )


# Skip reason for a file that needs a password; `rekey --filetypes` clears it if the file turns out readable.
ENCRYPTED_SKIP = "encrypted: needs a password to read"
# Analytics that handle encryption themselves (archive extraction tries known passwords).
READS_ENCRYPTED = frozenset({EnrichmentType.ARCHIVE_EXTRACTION})
# An encrypted email's headers are still readable, so email parsing (text extraction) still runs.
READS_ENCRYPTED_GROUPS = {EnrichmentType.TEXT_EXTRACTION: frozenset({"email"})}


def reads_encrypted(enrichment_type: EnrichmentType, filetype_group: str) -> bool:
    """Whether this analytic gets something from an encrypted file of this group."""
    return enrichment_type in READS_ENCRYPTED or filetype_group in READS_ENCRYPTED_GROUPS.get(
        enrichment_type, frozenset()
    )


def _file_enrichment(
    file_id: str, enrichment_type: EnrichmentType, *, is_encrypted: bool, filetype_group: str
) -> EnrichmentTable:
    """A new row for a file: PENDING, or SKIPPED when the file is encrypted and the analytic can't read it."""
    skip = is_encrypted and not reads_encrypted(enrichment_type, filetype_group)
    return EnrichmentTable(
        enrichable_type=EnrichableType.FILE,
        enrichable_id=file_id,
        enrichment_type=enrichment_type,
        status=ProcessingStatus.SKIPPED if skip else ProcessingStatus.PENDING,
        error_message=ENCRYPTED_SKIP if skip else None,
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
                await self.session.flush()
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
                run_id=claiming_run_id.get(),
                date_started=datetime.now(UTC),
                date_updated=datetime.now(UTC),
            )
        )
        await self.session.execute(statement)

    async def get_enrichment_ids_for(
        self,
        enrichable_ids: list[str],
        enrichment_type: EnrichmentType,
        enrichable_type: EnrichableType = EnrichableType.FILE,
    ) -> dict[str, str]:
        """`{enrichable_id: enrichment_id}` for the given rows and type.

        Used by the combined LLM pass to complete a second enrichment type's rows
        for the same files it just processed under the primary type.
        """
        if not enrichable_ids:
            return {}
        rows = (
            await self.session.execute(
                select(EnrichmentTable.enrichable_id, EnrichmentTable.id).where(
                    EnrichmentTable.enrichable_type == enrichable_type,
                    EnrichmentTable.enrichment_type == enrichment_type,
                    EnrichmentTable.enrichable_id.in_(enrichable_ids),
                )
            )
        ).all()
        return {enrichable_id: enrichment_id for enrichable_id, enrichment_id in rows}

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

    async def mark_skipped(self, reasons: dict[str, str]) -> None:
        """Mark enrichments SKIPPED, each with why (kept in `error_message`, shown as the skip breakdown)."""
        by_reason: dict[str, list[str]] = {}
        for enrichment_id, reason in reasons.items():
            by_reason.setdefault(reason, []).append(enrichment_id)
        for reason, enrichment_ids in by_reason.items():
            await self.session.execute(
                update(EnrichmentTable)
                .where(EnrichmentTable.id.in_(enrichment_ids))
                .values(status=ProcessingStatus.SKIPPED, error_message=reason, date_updated=datetime.now(UTC))
            )

    async def mark_failed(self, failures: dict[str, str | BaseException], increment_retry: bool = True) -> None:
        """Mark enrichments FAILED, each with why -- an exception or a message, shown in the failures dialog."""
        by_message: dict[str, list[str]] = {}
        for enrichment_id, reason in failures.items():
            message = f"{type(reason).__name__}: {reason}" if isinstance(reason, BaseException) else reason
            by_message.setdefault(message[:2000], []).append(enrichment_id)

        for message, enrichment_ids in by_message.items():
            values = {"status": ProcessingStatus.FAILED, "error_message": message, "date_updated": datetime.now(UTC)}
            if increment_retry:
                values["retry_count"] = EnrichmentTable.retry_count + 1
            await self.session.execute(
                update(EnrichmentTable).where(EnrichmentTable.id.in_(enrichment_ids)).values(**values)
            )

    async def release_claims(self, enrichment_ids: list[str]) -> None:
        """Return this run's claims to PENDING untouched (no error, no retry spent): the run stopped, the files didn't fail."""
        await self.session.execute(
            update(EnrichmentTable)
            .where(EnrichmentTable.id.in_(enrichment_ids))
            .values(status=ProcessingStatus.PENDING, date_started=None, date_updated=datetime.now(UTC))
        )

    async def reset_stuck_enrichments(
        self,
        stuck_threshold_minutes: int = 60,
        enrichment_type: EnrichmentType | None = None,
        dataset_id: str | None = None,
    ) -> int:
        """Return orphaned PROCESSING claims (from an interrupted run) to PENDING.

        A claim is orphaned when the run that made it is no longer alive (no fresh heartbeat).
        Claims made outside any recorded run fall back to their age.

        Args:
            stuck_threshold_minutes: Age past which a claim with no run is reset.
            enrichment_type: Limit to one analytic.
            dataset_id: Limit to file enrichments in one dataset.

        Returns:
            Number of rows reset.
        """
        threshold = datetime.now(UTC) - timedelta(minutes=stuck_threshold_minutes)
        statement = (
            update(EnrichmentTable)
            .where(
                EnrichmentTable.status == ProcessingStatus.PROCESSING,
                or_(
                    and_(EnrichmentTable.run_id.is_(None), EnrichmentTable.date_started < threshold),
                    and_(EnrichmentTable.run_id.is_not(None), EnrichmentTable.run_id.not_in(live_run_ids())),
                ),
            )
            .values(
                status=ProcessingStatus.PENDING,
                run_id=None,
                date_started=None,
                date_updated=datetime.now(UTC),
            )
        )
        if enrichment_type:
            statement = statement.where(EnrichmentTable.enrichment_type == enrichment_type)
        if dataset_id:
            statement = statement.where(
                EnrichmentTable.enrichable_type == EnrichableType.FILE,
                EnrichmentTable.enrichable_id.in_(select(FileTable.id).where(FileTable.dataset_id == dataset_id)),
            )
        result = await self.session.execute(statement)
        await self.session.commit()
        return result.rowcount or 0

    async def gated_stage_counts(
        self, *, dataset_id: str, enrichment_type: EnrichmentType, scored_tag: str, calendar_filetype: str | None = None
    ) -> list[tuple[bool, ProcessingStatus, bool, str | None, int]]:
        """`(is_calendar_file, status, has_gate_score, skip_reason, count)` for a gated analytic's rows in a dataset."""
        is_calendar = (FileTable.filetype == calendar_filetype) if calendar_filetype else literal(False)
        scored = FileTable.tag_scores.has_key(scored_tag)
        reason = case((EnrichmentTable.status == ProcessingStatus.SKIPPED, EnrichmentTable.error_message), else_=None)
        rows = await self.session.execute(
            select(is_calendar, EnrichmentTable.status, scored, reason, func.count())
            .join(FileTable, EnrichmentTable.enrichable_id == FileTable.id)
            .where(
                EnrichmentTable.enrichable_type == EnrichableType.FILE,
                EnrichmentTable.enrichment_type == enrichment_type,
                FileTable.dataset_id == dataset_id,
            )
            .group_by(is_calendar, EnrichmentTable.status, scored, reason)
        )
        return [(bool(cal), ProcessingStatus(st), bool(has), why, n) for cal, st, has, why, n in rows.all()]

    async def get_skip_reasons(self, *, dataset_id: str) -> dict[EnrichmentType, dict[str, int]]:
        """Per analytic, why its skipped rows in a dataset were skipped -> count."""
        rows = await self.session.execute(
            select(
                EnrichmentTable.enrichment_type,
                func.coalesce(EnrichmentTable.error_message, "no reason recorded"),
                func.count(),
            )
            .join(FileTable, EnrichmentTable.enrichable_id == FileTable.id)
            .where(
                EnrichmentTable.enrichable_type == EnrichableType.FILE,
                EnrichmentTable.status == ProcessingStatus.SKIPPED,
                FileTable.dataset_id == dataset_id,
            )
            .group_by(EnrichmentTable.enrichment_type, EnrichmentTable.error_message)
        )
        reasons: dict[EnrichmentType, dict[str, int]] = defaultdict(dict)
        for enrichment_type, reason, n in rows.all():
            reasons[EnrichmentType(enrichment_type)][reason] = n
        return reasons

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

    async def get_failure_reason_summary(
        self, dataset_id: str, enrichment_type: EnrichmentType
    ) -> list[tuple[str | None, int]]:
        """Distinct failure messages for a dataset + analytic, most common first."""
        count = func.count(EnrichmentTable.id)
        statement = (
            select(EnrichmentTable.error_message, count)
            .join(
                FileTable,
                (EnrichmentTable.enrichable_id == FileTable.id)
                & (EnrichmentTable.enrichable_type == EnrichableType.FILE),
            )
            .where(
                EnrichmentTable.enrichment_type == enrichment_type,
                EnrichmentTable.status == ProcessingStatus.FAILED,
                FileTable.dataset_id == dataset_id,
            )
            .group_by(EnrichmentTable.error_message)
            .order_by(count.desc())
        )
        result = await self.session.execute(statement)
        return [(message, n) for message, n in result.all()]

    async def get_failed_enrichments(
        self,
        dataset_id: str,
        enrichment_type: EnrichmentType,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[int, list[dict]]:
        """Failed enrichment rows for a dataset + analytic, newest first, with file identity."""
        join_condition = (EnrichmentTable.enrichable_id == FileTable.id) & (
            EnrichmentTable.enrichable_type == EnrichableType.FILE
        )
        filters = (
            EnrichmentTable.enrichment_type == enrichment_type,
            EnrichmentTable.status == ProcessingStatus.FAILED,
            FileTable.dataset_id == dataset_id,
        )

        total = await self.session.scalar(
            select(func.count(EnrichmentTable.id)).join(FileTable, join_condition).where(*filters)
        )

        statement = (
            select(EnrichmentTable, FileTable)
            .join(FileTable, join_condition)
            .where(*filters)
            .order_by(EnrichmentTable.date_updated.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(statement)
        items = [
            {"enrichment": Enrichment.model_validate(enrichment), "file": file} for enrichment, file in result.all()
        ]
        return total or 0, items

    async def retry_failed_enrichments(
        self,
        enrichment_ids: list[str] | None = None,
        enrichment_type: EnrichmentType | None = None,
        enrichable_type: EnrichableType | None = None,
        dataset_id: str | None = None,
    ) -> int:
        """Reset failed enrichments back to pending with a fresh retry budget."""
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
                retry_count=0,
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

    async def delete_unfinished_for_files(self, file_ids: list[str]) -> int:
        """Drop these files' not-yet-completed enrichment rows, e.g. ones queued under a wrong filetype."""
        result = await self.session.execute(
            delete(EnrichmentTable).where(
                EnrichmentTable.enrichable_type == EnrichableType.FILE,
                EnrichmentTable.enrichable_id.in_(file_ids),
                EnrichmentTable.status != ProcessingStatus.COMPLETED,
            )
        )
        return result.rowcount or 0

    async def delete_by_type(
        self,
        dataset_id: str,
        enrichment_type: EnrichmentType,
        enrichable_type: EnrichableType = EnrichableType.FILE,
    ) -> int:
        """Delete a dataset's enrichment rows of one type, e.g. to force a clean re-run.

        `queue_enrichments_by_filter` only queues files *lacking* an
        enrichment row -- an already-COMPLETED one is otherwise never
        revisited, so deleting it here (rather than resetting it to PENDING)
        is what makes the next `queue_enrichments_by_filter` call re-create
        it and pick the file back up.
        """
        file_ids = select(FileTable.id).where(FileTable.dataset_id == dataset_id)
        statement = delete(EnrichmentTable).where(
            EnrichmentTable.enrichable_type == enrichable_type,
            EnrichmentTable.enrichment_type == enrichment_type,
            EnrichmentTable.enrichable_id.in_(file_ids),
        )
        result = await self.session.execute(statement)
        await self.session.commit()
        return result.rowcount or 0

    async def delete_by_dataset_files(self, dataset_id: str) -> int:
        """Delete FILE-type enrichments for every file in a dataset.

        `enrichable_id` is polymorphic (no real FK), so these rows don't
        cascade-delete when a dataset's files do -- called before deleting a
        dataset to avoid leaving orphaned enrichment rows behind.
        """
        file_ids = select(FileTable.id).where(FileTable.dataset_id == dataset_id)
        statement = delete(EnrichmentTable).where(
            EnrichmentTable.enrichable_type == EnrichableType.FILE,
            EnrichmentTable.enrichable_id.in_(file_ids),
        )
        result = await self.session.execute(statement)
        await self.session.commit()
        return result.rowcount or 0

    async def count_pending(
        self,
        enrichment_type: EnrichmentType | None = None,
        enrichable_type: EnrichableType | None = None,
        dataset_id: str | None = None,
        filetype_group_filter: str | None = None,
    ) -> int:
        """Count pending enrichments."""
        statement = select(func.count(EnrichmentTable.id)).where(EnrichmentTable.status == ProcessingStatus.PENDING)

        if enrichment_type:
            statement = statement.where(EnrichmentTable.enrichment_type == enrichment_type)

        if enrichable_type:
            statement = statement.where(EnrichmentTable.enrichable_type == enrichable_type)

        if dataset_id or filetype_group_filter:
            statement = statement.join(
                FileTable,
                (EnrichmentTable.enrichable_id == FileTable.id)
                & (EnrichmentTable.enrichable_type == EnrichableType.FILE),
            )
            if dataset_id:
                statement = statement.where(FileTable.dataset_id == dataset_id)
            if filetype_group_filter:
                statement = statement.where(FileTable.filetype_group == filetype_group_filter)

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

        count = 0
        for file in files:
            self.session.add(
                _file_enrichment(
                    file.id, enrichment_type, is_encrypted=file.is_encrypted, filetype_group=file.filetype_group
                )
            )
            count += 1

        await self.session.flush()
        logger.info(f"Queued {count} {enrichment_type.value} enrichments")
        return count

    async def queue_files_with_text(
        self, *, dataset_id: str, enrichment_type: EnrichmentType, filetype_group: str
    ) -> int:
        """Queue `enrichment_type` for files of `filetype_group` that have extracted text and no row yet.

        For groups where text is the exception (images only have it after OCR; tables only when
        their text extraction was opted into), so text consumers don't queue files they'd skip.
        """
        from cipher.datastores.postgres.tables.extracted_text import ExtractedTextTable

        query = (
            select(FileTable.id)
            .join(ExtractedTextTable, ExtractedTextTable.file_id == FileTable.id)
            .outerjoin(
                EnrichmentTable,
                (EnrichmentTable.enrichable_id == FileTable.id)
                & (EnrichmentTable.enrichable_type == EnrichableType.FILE)
                & (EnrichmentTable.enrichment_type == enrichment_type),
            )
            .where(
                EnrichmentTable.id.is_(None),
                FileTable.dataset_id == dataset_id,
                FileTable.filetype_group == filetype_group,
            )
        )
        file_ids = [file_id for (file_id,) in (await self.session.execute(query)).all()]
        return await self.queue_enrichments_for_files(file_ids=file_ids, enrichment_type=enrichment_type)

    async def get_unqueued_files(
        self, dataset_id: str, enrichment_type: EnrichmentType, filetypes: list[str]
    ) -> list[dict]:
        """`{id, sha256, filetype, filetype_group}` of a dataset's files of `filetypes` with no `enrichment_type` row.

        For enrichments that filter candidates beyond filetype (e.g. OCR's CLIP
        gate) before calling `queue_enrichments_for_files`.
        """
        query = (
            select(FileTable.id, FileTable.sha256, FileTable.filetype, FileTable.filetype_group)
            .outerjoin(
                EnrichmentTable,
                (EnrichmentTable.enrichable_id == FileTable.id)
                & (EnrichmentTable.enrichable_type == EnrichableType.FILE)
                & (EnrichmentTable.enrichment_type == enrichment_type),
            )
            .where(EnrichmentTable.id.is_(None), FileTable.dataset_id == dataset_id, FileTable.filetype.in_(filetypes))
        )
        return [dict(row._mapping) for row in (await self.session.execute(query)).all()]

    async def queue_enrichments_for_files(self, file_ids: list[str], enrichment_type: EnrichmentType) -> int:
        """Queue PENDING `enrichment_type` rows for exactly these files (callers pass unqueued ids).

        An encrypted file (`is_encrypted`: reading it needs a password) is recorded SKIPPED with
        `ENCRYPTED_SKIP` instead, so no analytic tries to read it; archive extraction is exempt.
        """
        encrypted: dict[str, str] = {}
        if file_ids and enrichment_type not in READS_ENCRYPTED:
            rows = await self.session.execute(
                select(FileTable.id, FileTable.filetype_group).where(FileTable.id.in_(file_ids), FileTable.is_encrypted)
            )
            encrypted = dict(rows.tuples().all())
        self.session.add_all(
            _file_enrichment(
                file_id,
                enrichment_type,
                is_encrypted=file_id in encrypted,
                filetype_group=encrypted.get(file_id, ""),
            )
            for file_id in file_ids
        )
        await self.session.flush()
        return len(file_ids)

    async def requeue(self, file_ids: list[str], enrichment_type: EnrichmentType, create_missing: bool = False) -> int:
        """Put these files' `enrichment_type` rows back to PENDING (fresh retries), e.g. after their text changed.

        With `create_missing`, files lacking a row get one -- for enrichments whose
        own queueing wouldn't pick these files up (e.g. text embedding for images).
        """
        if not file_ids:
            return 0
        result = await self.session.execute(
            update(EnrichmentTable)
            .where(
                EnrichmentTable.enrichable_type == EnrichableType.FILE,
                EnrichmentTable.enrichment_type == enrichment_type,
                EnrichmentTable.enrichable_id.in_(file_ids),
            )
            .values(status=ProcessingStatus.PENDING, retry_count=0, error_message=None, date_updated=datetime.now(UTC))
            .returning(EnrichmentTable.enrichable_id)
        )
        existing = set(result.scalars().all())
        created = 0
        if create_missing:
            created = await self.queue_enrichments_for_files(
                [file_id for file_id in file_ids if file_id not in existing], enrichment_type
            )
        return len(existing) + created
