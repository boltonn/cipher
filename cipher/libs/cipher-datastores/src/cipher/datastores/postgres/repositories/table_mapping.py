"""Stored table mappings (one per dataset + header layout) and the files that use them.

A file's sheets point at a mapping through `file.table_sheets[].fingerprint`; its
emit progress is its `table_extraction` enrichment row. See docs/tabular-mapping.md.
"""

from datetime import UTC, datetime

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.enrichment import EnrichmentTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.table_mapping import TableMappingTable
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType, ProcessingStatus
from cipher.schemas.ingestion.table_mapping import (
    OTHER_FIELD,
    TableMapping,
    TableMappingDetail,
    TableMappingFile,
    TableMappingFileStatus,
    TableMappingRecord,
    TableMappingStatus,
    TableMappingSummary,
    TableSample,
    TableSheetLayout,
)

_FILE_STATUS = {
    ProcessingStatus.COMPLETED: TableMappingFileStatus.EMITTED,
    ProcessingStatus.FAILED: TableMappingFileStatus.FAILED,
}


def _record(row: TableMappingTable) -> TableMappingRecord:
    return TableMappingRecord(
        id=row.id,
        dataset_id=row.dataset_id,
        fingerprint=row.fingerprint,
        mapping=TableMapping.model_validate(row.mapping),
        sample=TableSample.model_validate(row.sample or {}),
        is_verified=row.is_verified,
        verified_by=row.verified_by,
        date_verified=row.date_verified,
        date_created=row.date_created,
        date_updated=row.date_updated,
    )


def _uses_fingerprint(fingerprint):  # noqa: ANN001, ANN202 -- a SQL expression over `file`
    return FileTable.table_sheets.op("@>")(func.jsonb_build_array(func.jsonb_build_object("fingerprint", fingerprint)))


class PostgresTableMappingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, mapping_id: str) -> TableMappingRecord | None:
        """One mapping by id."""
        row = await self.session.get(TableMappingTable, mapping_id)
        return _record(row) if row else None

    async def get_by_fingerprint(self, *, dataset_id: str, fingerprint: str) -> TableMappingRecord | None:
        """The dataset's mapping for a header layout."""
        row = (
            await self.session.execute(
                select(TableMappingTable).where(
                    TableMappingTable.dataset_id == dataset_id, TableMappingTable.fingerprint == fingerprint
                )
            )
        ).scalar_one_or_none()
        return _record(row) if row else None

    async def add_proposal(
        self, *, dataset_id: str, mapping: TableMapping, sample: TableSample
    ) -> tuple[TableMappingRecord, bool]:
        """Store a model proposal unless the layout already has a mapping (which may hold user edits). Returns (record, created)."""
        inserted = (
            await self.session.execute(
                pg_insert(TableMappingTable)
                .values(
                    dataset_id=dataset_id,
                    fingerprint=mapping.fingerprint,
                    mapping=mapping.model_dump(mode="json"),
                    sample=sample.model_dump(mode="json"),
                )
                .on_conflict_do_nothing(constraint="uq_table_mapping_dataset_fingerprint")
                .returning(TableMappingTable.id)
            )
        ).scalar_one_or_none()
        record = await self.get_by_fingerprint(dataset_id=dataset_id, fingerprint=mapping.fingerprint)
        assert record is not None
        return record, inserted is not None

    async def save(self, mapping_id: str, *, mapping: TableMapping) -> TableMappingRecord | None:
        """Replace a mapping after an edit; any edit clears verification."""
        await self.session.execute(
            update(TableMappingTable)
            .where(TableMappingTable.id == mapping_id)
            .values(
                mapping=mapping.model_dump(mode="json"),
                is_verified=False,
                verified_by=None,
                date_verified=None,
                date_updated=datetime.now(UTC),
            )
        )
        await self.session.commit()
        return await self.get(mapping_id)

    async def set_verified(self, mapping_id: str, *, user_id: str | None) -> TableMappingRecord | None:
        """Mark a mapping verified by `user_id` (from the session, never the request)."""
        now = datetime.now(UTC)
        await self.session.execute(
            update(TableMappingTable)
            .where(TableMappingTable.id == mapping_id)
            .values(is_verified=True, verified_by=user_id, date_verified=now, date_updated=now)
        )
        await self.session.commit()
        return await self.get(mapping_id)

    async def set_file_sheets(self, *, file_id: str, sheets: list[TableSheetLayout]) -> None:
        """Record a file's sheet layouts (`[]` = profiled, nothing tabular found)."""
        await self.session.execute(
            update(FileTable)
            .where(FileTable.id == file_id)
            .values(table_sheets=[s.model_dump(mode="json") for s in sheets])
        )

    async def file_ids(self, *, dataset_id: str, fingerprint: str) -> list[str]:
        """Files in the dataset with a sheet of this layout."""
        rows = await self.session.execute(
            select(FileTable.id).where(FileTable.dataset_id == dataset_id, _uses_fingerprint(fingerprint))
        )
        return [r for (r,) in rows.all()]

    async def verified_fingerprints(self, *, dataset_id: str) -> dict[str, TableMappingRecord]:
        """Verified mappings by fingerprint -- what `emit-tables` may write."""
        rows = (
            await self.session.execute(
                select(TableMappingTable).where(
                    TableMappingTable.dataset_id == dataset_id, TableMappingTable.is_verified.is_(True)
                )
            )
        ).scalars()
        return {row.fingerprint: _record(row) for row in rows}

    async def files(self, record: TableMappingRecord) -> list[TableMappingFile]:
        """The files (one entry per matching sheet) using a mapping, with their emit status."""
        stmt = (
            select(FileTable.id, FileTable.sha256, FileTable.filename, FileTable.table_sheets, EnrichmentTable.status)
            .outerjoin(
                EnrichmentTable,
                and_(
                    EnrichmentTable.enrichable_id == FileTable.id,
                    EnrichmentTable.enrichable_type == EnrichableType.FILE,
                    EnrichmentTable.enrichment_type == EnrichmentType.TABLE_EXTRACTION,
                ),
            )
            .where(FileTable.dataset_id == record.dataset_id, _uses_fingerprint(record.fingerprint))
            .order_by(FileTable.filename)
        )
        out = []
        for file_id, sha256, filename, sheets, status in (await self.session.execute(stmt)).all():
            for sheet in sheets or []:
                if sheet.get("fingerprint") != record.fingerprint:
                    continue
                file_status = _FILE_STATUS.get(status) or (
                    TableMappingFileStatus.QUEUED if record.is_verified else TableMappingFileStatus.WAITING
                )
                out.append(
                    TableMappingFile(
                        file_id=file_id,
                        sha256=sha256,
                        filename=filename,
                        sheet=sheet.get("sheet"),
                        rows_estimate=sheet.get("rows_estimate"),
                        status=file_status,
                    )
                )
        return out

    async def detail(self, mapping_id: str) -> TableMappingDetail | None:
        """A mapping with its files."""
        record = await self.get(mapping_id)
        if record is None:
            return None
        return TableMappingDetail(**record.model_dump(), files=await self.files(record))

    async def for_table(
        self, sha256: str, *, dataset_ids: list[str] | None, dataset_id: str | None = None
    ) -> tuple[dict | None, list[TableMappingDetail]]:
        """A table by content hash: one of its files (in `dataset_id` if given) and the mapping of each of its sheets.

        Content-identical files share a hash; the mapping comes from the dataset of the file picked.
        `dataset_ids=None` means any dataset (admin).
        """
        stmt = select(FileTable.id, FileTable.filename, FileTable.dataset_id, FileTable.table_sheets).where(
            FileTable.sha256 == sha256
        )
        if dataset_ids is not None:
            stmt = stmt.where(FileTable.dataset_id.in_(dataset_ids))
        rows = (await self.session.execute(stmt.order_by(FileTable.table_sheets.is_(None), FileTable.filename))).all()
        row = next((r for r in rows if r.dataset_id == dataset_id), rows[0] if rows else None)
        if row is None:
            return None, []
        file = {"id": row.id, "filename": row.filename, "dataset_id": row.dataset_id}
        out = []
        for sheet in row.table_sheets or []:
            record = await self.get_by_fingerprint(dataset_id=row.dataset_id, fingerprint=sheet["fingerprint"])
            if record is not None:
                out.append(TableMappingDetail(**record.model_dump(), files=await self.files(record)))
        return file, out

    async def list_summaries(self, *, dataset_ids: list[str]) -> list[TableMappingSummary]:
        """Every mapping in the datasets, unverified first, with file and row counts."""
        rows = (
            (
                await self.session.execute(
                    select(TableMappingTable)
                    .where(TableMappingTable.dataset_id.in_(dataset_ids))
                    .order_by(TableMappingTable.is_verified, TableMappingTable.date_updated.desc())
                )
            )
            .scalars()
            .all()
        )
        counts = await self._file_counts(dataset_ids=dataset_ids)
        out = []
        for row in rows:
            mapping = TableMapping.model_validate(row.mapping)
            files, row_total, emitted = counts.get((row.dataset_id, row.fingerprint), (0, 0, 0))
            out.append(
                TableMappingSummary(
                    id=row.id,
                    dataset_id=row.dataset_id,
                    fingerprint=row.fingerprint,
                    sheet=mapping.sheet,
                    format=mapping.format,
                    headers=[c.header for c in mapping.columns],
                    column_count=len(mapping.columns),
                    typed_column_count=sum(1 for c in mapping.columns if c.field_type != OTHER_FIELD),
                    slot_count=len(mapping.slots),
                    edge_count=sum(1 for e in mapping.edges if e.is_enabled),
                    file_count=files,
                    rows_estimate=row_total,
                    emitted_file_count=emitted,
                    status=TableMappingStatus.VERIFIED if row.is_verified else TableMappingStatus.NEEDS_REVIEW,
                    verified_by=row.verified_by,
                    date_verified=row.date_verified,
                    date_updated=row.date_updated,
                )
            )
        return out

    async def _file_counts(self, *, dataset_ids: list[str]) -> dict[tuple[str, str], tuple[int, int, int]]:
        """(dataset, fingerprint) -> (files, summed row estimate, files emitted)."""
        result = await self.session.execute(
            text(
                """
                SELECT f.dataset_id, s->>'fingerprint' AS fingerprint,
                       count(DISTINCT f.id) AS files,
                       coalesce(sum((s->>'rows_estimate')::bigint), 0) AS rows_estimate,
                       count(DISTINCT f.id) FILTER (WHERE e.status = 'COMPLETED') AS emitted
                FROM file f
                CROSS JOIN LATERAL jsonb_array_elements(f.table_sheets) s
                LEFT JOIN enrichment e
                  ON e.enrichable_id = f.id AND e.enrichable_type = 'FILE' AND e.enrichment_type = 'TABLE_EXTRACTION'
                WHERE f.dataset_id = ANY(:dataset_ids) AND f.table_sheets IS NOT NULL
                GROUP BY 1, 2
                """
            ),
            {"dataset_ids": dataset_ids},
        )
        return {(r.dataset_id, r.fingerprint): (r.files, int(r.rows_estimate), r.emitted) for r in result}
