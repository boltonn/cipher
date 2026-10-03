"""Database metrics repository - table sizes and an estimated per-dataset breakdown."""

from collections import defaultdict

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.dataset import DatasetTable
from cipher.schemas.ingestion.database_metrics import (
    DatabaseMetrics,
    DatasetDatabaseUsage,
    DatasetTableUsage,
    TableMetrics,
    TableScope,
)

_TABLES_SQL = text("""
    SELECT c.relname,
           pg_total_relation_size(c.oid),
           pg_indexes_size(c.oid),
           c.reltuples::bigint,
           bool_or(a.attname = 'dataset_id'),
           bool_or(a.attname = 'file_id')
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
    GROUP BY c.oid, c.relname
    ORDER BY pg_total_relation_size(c.oid) DESC
""")


def _scope(has_dataset_id: bool, has_file_id: bool) -> TableScope:
    if has_dataset_id:
        return TableScope.DATASET
    return TableScope.FILE if has_file_id else TableScope.SHARED


class PostgresDatabaseMetricsRepository:
    """Read-only Postgres size metrics, overall and per dataset."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _tables(self) -> list[TableMetrics]:
        return [
            TableMetrics(
                name=name,
                scope=_scope(has_dataset_id, has_file_id),
                total_bytes=total,
                index_bytes=indexes,
                row_count=rows if rows >= 0 else None,
            )
            for name, total, indexes, rows, has_dataset_id, has_file_id in (
                await self.session.execute(_TABLES_SQL)
            ).all()
        ]

    async def _dataset_row_counts(self, table: TableMetrics, dataset_id: str | None) -> tuple[dict[str, int], int]:
        """Rows per dataset in one attributable table (only `dataset_id` when given), plus the table's row count."""
        dataset_column = "t.dataset_id" if table.scope == TableScope.DATASET else "f.dataset_id"
        join = "" if table.scope == TableScope.DATASET else "JOIN file f ON f.id = t.file_id"
        where = "" if dataset_id is None else f"WHERE {dataset_column} = :dataset_id"
        statement = text(f'SELECT {dataset_column}, count(*) FROM "{table.name}" t {join} {where} GROUP BY 1')
        rows = (await self.session.execute(statement, {"dataset_id": dataset_id})).all()
        total = (await self.session.execute(text(f'SELECT count(*) FROM "{table.name}"'))).scalar_one()
        return {key: count for key, count in rows if key is not None}, total

    async def _dataset_usage(self, tables: list[TableMetrics], dataset_id: str | None) -> list[DatasetDatabaseUsage]:
        usage: dict[str, list[DatasetTableUsage]] = defaultdict(list)
        for table in tables:
            if table.scope == TableScope.SHARED:
                continue
            counts, total = await self._dataset_row_counts(table=table, dataset_id=dataset_id)
            for key, count in counts.items():
                share = count / max(total, 1)
                usage[key].append(
                    DatasetTableUsage(
                        table_name=table.name,
                        row_count=count,
                        estimated_bytes=round(table.total_bytes * share),
                        estimated_index_bytes=round(table.index_bytes * share),
                    )
                )
        names = dict(
            (
                await self.session.execute(
                    text("SELECT id, name FROM dataset WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
                    {"ids": list(usage) or [""]},
                )
            ).all()
        )
        datasets = [
            DatasetDatabaseUsage(
                dataset_id=key,
                dataset_name=names.get(key, key),
                row_count=sum(table.row_count for table in table_usage),
                estimated_bytes=sum(table.estimated_bytes for table in table_usage),
                estimated_index_bytes=sum(table.estimated_index_bytes for table in table_usage),
                tables=sorted(table_usage, key=lambda table: table.estimated_bytes, reverse=True),
            )
            for key, table_usage in usage.items()
        ]
        return sorted(datasets, key=lambda dataset: dataset.estimated_bytes, reverse=True)

    async def get_metrics(self) -> DatabaseMetrics:
        """Database size, every table's footprint, and each dataset's estimated share."""
        size = (await self.session.execute(text("SELECT pg_database_size(current_database())"))).scalar_one()
        tables = await self._tables()
        return DatabaseMetrics(
            database_size_bytes=size, tables=tables, datasets=await self._dataset_usage(tables=tables, dataset_id=None)
        )

    async def get_dataset_usage(self, dataset_id: str) -> DatasetDatabaseUsage | None:
        """One dataset's estimated share of each table; None if the dataset doesn't exist."""
        dataset = await self.session.get(DatasetTable, dataset_id)
        if dataset is None:
            return None
        datasets = await self._dataset_usage(tables=await self._tables(), dataset_id=dataset_id)
        return (
            datasets[0]
            if datasets
            else DatasetDatabaseUsage(
                dataset_id=dataset_id,
                dataset_name=dataset.name,
                row_count=0,
                estimated_bytes=0,
                estimated_index_bytes=0,
            )
        )
