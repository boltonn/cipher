"""Read/write `search` records -- stored questions, never results (docs/global-search.md §7)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.search import SearchTable, new_search_id
from cipher.schemas.interaction.search_record import PaginatedSearchHistory, SearchRecord, SearchRequest


class PostgresSearchRecordRepository:
    """Upsert a user's searches by fingerprint; read one or their history; prune old unsaved ones."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(self, *, user_id: str, request: SearchRequest) -> SearchRecord:
        """Store `request` for `user_id`, or bump the existing record of the same question."""
        now = datetime.now(UTC)
        statement = (
            pg_insert(SearchTable)
            .values(
                id=new_search_id(),
                user_id=user_id,
                query=request.query.strip(),
                dataset_ids=sorted(request.dataset_ids),
                filters=request.filters.model_dump(mode="json"),
                parent_id=request.parent_id,
                fingerprint=request.fingerprint(user_id=user_id),
                run_count=1,
                date_created=now,
                date_last_run=now,
            )
            .on_conflict_do_update(
                index_elements=[SearchTable.fingerprint],
                set_={"run_count": SearchTable.run_count + 1, "date_last_run": now},
            )
            .returning(SearchTable)
        )
        row = (await self.session.execute(statement)).scalar_one()
        await self.session.commit()
        return SearchRecord.model_validate(row)

    async def get(self, search_id: str) -> SearchRecord | None:
        """One record by id, regardless of owner -- the caller enforces privacy."""
        row = await self.session.get(SearchTable, search_id)
        return SearchRecord.model_validate(row) if row else None

    async def trail(self, search_id: str, *, max_steps: int = 20) -> list[SearchRecord]:
        """`search_id` and the searches it was narrowed from, oldest first (same owner only)."""
        rows = await self.session.execute(
            text(
                "WITH RECURSIVE chain AS ("
                "  SELECT s.*, 0 AS depth FROM search s WHERE s.id = :id"
                "  UNION ALL"
                "  SELECT p.*, chain.depth + 1 FROM search p JOIN chain ON p.id = chain.parent_id"
                "  WHERE p.user_id = chain.user_id AND chain.depth < :max_steps"
                ") SELECT * FROM chain ORDER BY depth DESC"
            ),
            {"id": search_id, "max_steps": max_steps},
        )
        return [SearchRecord.model_validate(dict(row)) for row in rows.mappings()]

    async def get_ai(self, search_id: str) -> dict | None:
        """The cached AI reading of this search (answer, suggestion), if any."""
        return (await self.session.execute(select(SearchTable.llm_plan).where(SearchTable.id == search_id))).scalar()

    async def save_ai(self, search_id: str, reading: dict) -> None:
        """Cache the AI reading so Back/reload never asks the model again."""
        await self.session.execute(update(SearchTable).where(SearchTable.id == search_id).values(llm_plan=reading))
        await self.session.commit()

    async def history(
        self, *, user_id: str, saved: bool | None = None, page: int = 1, limit: int = 20
    ) -> PaginatedSearchHistory:
        """`user_id`'s searches, most recently run first; `saved` keeps only saved (True) or unsaved (False) ones."""
        conditions = [SearchTable.user_id == user_id]
        if saved is not None:
            conditions.append(SearchTable.date_saved.is_not(None) if saved else SearchTable.date_saved.is_(None))
        total = (
            await self.session.execute(select(func.count()).select_from(SearchTable).where(*conditions))
        ).scalar_one()
        rows = (
            await self.session.execute(
                select(SearchTable)
                .where(*conditions)
                .order_by(SearchTable.date_last_run.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).scalars()
        return PaginatedSearchHistory(
            total=total, page=page, limit=limit, data=[SearchRecord.model_validate(row) for row in rows]
        )

    async def set_saved(self, search_id: str, *, saved: bool, name: str | None = None) -> SearchRecord:
        """Save (kept past pruning, optionally named) or unsave a search."""
        values = {"date_saved": datetime.now(UTC), "name": name} if saved else {"date_saved": None, "name": None}
        statement = update(SearchTable).where(SearchTable.id == search_id).values(**values).returning(SearchTable)
        record = SearchRecord.model_validate((await self.session.execute(statement)).scalar_one())
        await self.session.commit()
        return record

    async def prune(self, *, retention_days: int) -> int:
        """Delete unsaved searches not run in `retention_days`; saved ones are kept."""
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        result = await self.session.execute(
            delete(SearchTable).where(SearchTable.date_saved.is_(None), SearchTable.date_last_run < cutoff)
        )
        await self.session.commit()
        return result.rowcount
