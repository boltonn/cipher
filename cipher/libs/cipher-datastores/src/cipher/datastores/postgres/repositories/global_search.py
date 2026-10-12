"""Name lookups for the global-search overview lanes (files, events, places) -- trigram-indexed `ILIKE`.

Totals are capped: counting stops at `cap + 1` rows, so a common word never pays for an exact count.
Lookups run with only the trigram (bitmap) path allowed: with a `LIMIT`, the planner otherwise walks
a plain btree index hoping for early matches -- 145 ms instead of 1 ms for a moderately rare filename.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.repositories.location import _to_schema as location_to_schema
from cipher.datastores.postgres.tables.event import EventTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.location import LocationTable
from cipher.schemas.graph.event import Event
from cipher.schemas.graph.location import Location
from cipher.schemas.ingestion.file import File

COUNT_CAP = 100


def _like(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class PostgresGlobalSearchRepository:
    """Files by filename, events by title, places by name; each returns (items, total, total_is_exact)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @asynccontextmanager
    async def _trigram_only(self) -> AsyncIterator[None]:
        flags = ("enable_indexscan", "enable_indexonlyscan", "enable_seqscan")
        for flag in flags:
            await self.session.execute(text(f"SET LOCAL {flag} = off"))
        try:
            yield
        finally:
            for flag in flags:
                await self.session.execute(text(f"SET LOCAL {flag} = on"))

    async def _capped_count(self, statement, cap: int) -> tuple[int, bool]:
        count = (
            await self.session.execute(select(func.count()).select_from(statement.limit(cap + 1).subquery()))
        ).scalar_one()
        return min(count, cap), count <= cap

    async def files_by_name(
        self,
        *,
        query: str,
        dataset_ids: list[str] | None,
        filetype_groups: list[str] | None = None,
        limit: int = 5,
        cap: int = COUNT_CAP,
    ) -> tuple[list[File], int, bool]:
        """Files whose filename contains `query`, newest content first."""
        statement = select(FileTable).where(FileTable.filename.ilike(_like(query)))
        if dataset_ids is not None:
            statement = statement.where(FileTable.dataset_id.in_(dataset_ids))
        if filetype_groups:
            statement = statement.where(FileTable.filetype_group.in_(filetype_groups))
        async with self._trigram_only():
            rows = (
                await self.session.execute(statement.order_by(FileTable.date_created.desc().nulls_last()).limit(limit))
            ).scalars()
            total, exact = await self._capped_count(statement.with_only_columns(FileTable.id), cap)
        return [File.model_validate(row) for row in rows], total, exact

    async def events_by_title(
        self,
        *,
        query: str,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 3,
        cap: int = COUNT_CAP,
    ) -> tuple[list[Event], int, bool]:
        """Events whose title contains `query`, most recent first."""
        statement = select(EventTable).where(EventTable.title.ilike(_like(query)))
        if date_from:
            statement = statement.where(EventTable.date_start >= date_from)
        if date_to:
            statement = statement.where(EventTable.date_start < date_to)
        async with self._trigram_only():
            rows = (
                await self.session.execute(statement.order_by(EventTable.date_start.desc().nulls_last()).limit(limit))
            ).scalars()
            total, exact = await self._capped_count(statement.with_only_columns(EventTable.id), cap)
        return [Event.model_validate(row) for row in rows], total, exact

    async def places_by_name(
        self, *, query: str, limit: int = 3, cap: int = COUNT_CAP
    ) -> tuple[list[Location], int, bool]:
        """Locations whose name contains `query`."""
        statement = select(LocationTable).where(LocationTable.name.ilike(_like(query)))
        async with self._trigram_only():
            rows = (await self.session.execute(statement.order_by(LocationTable.name).limit(limit))).scalars()
            total, exact = await self._capped_count(statement.with_only_columns(LocationTable.id), cap)
        return [location_to_schema(row) for row in rows], total, exact
