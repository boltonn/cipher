from datetime import UTC, datetime

from sqlalchemy import asc, delete, desc, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.datastores.postgres.tables.entity_match import EntityMatchTable
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.schemas._base.common import SortOrder
from cipher.schemas.graph.entity_match import (
    EntityMatch,
    EntityMatchCreate,
    EntityMatchReview,
    EntityMatchSearchParameters,
    EntityMatchSortField,
    EntityMatchStatus,
    PaginatedEntityMatchesResponse,
)


class PostgresEntityMatchRepository:
    """Postgres datastore for candidate mention-to-entity resolutions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the entity_match table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(EntityMatchTable.metadata.create_all)

    async def create_match(self, match: EntityMatchCreate) -> EntityMatch:
        """Create a candidate resolution, returning the existing row if already proposed."""
        stmt = (
            pg_insert(EntityMatchTable)
            .values(**match.model_dump(by_alias=False))
            .on_conflict_do_nothing(constraint="uq_entity_match_mention_entity")
            .returning(EntityMatchTable)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        row = result.scalar_one_or_none()
        if row:
            return EntityMatch.model_validate(row)
        existing = await self.session.execute(
            select(EntityMatchTable).where(
                EntityMatchTable.mention_id == match.mention_id,
                EntityMatchTable.entity_id == match.entity_id,
            )
        )
        return EntityMatch.model_validate(existing.scalar_one())

    async def create_matches_batch(self, matches: list[EntityMatchCreate]) -> int:
        """Bulk-propose candidate resolutions, ignoring any already proposed."""
        if not matches:
            return 0
        stmt = (
            pg_insert(EntityMatchTable)
            .values([m.model_dump(by_alias=False) for m in matches])
            .on_conflict_do_nothing(constraint="uq_entity_match_mention_entity")
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return len(matches)

    async def get_match_by_id(self, match_id: str) -> EntityMatch | None:
        """Retrieve a candidate resolution by ID."""
        result = await self.session.execute(
            select(EntityMatchTable).where(EntityMatchTable.id == match_id)
        )
        row = result.scalar_one_or_none()
        return EntityMatch.model_validate(row) if row else None

    async def list_matches(self, request: EntityMatchSearchParameters) -> PaginatedEntityMatchesResponse:
        """Query the resolution review queue."""
        where = []
        if request.entity_id:
            where.append(EntityMatchTable.entity_id == request.entity_id)
        if request.mention_id:
            where.append(EntityMatchTable.mention_id == request.mention_id)
        if request.dataset_id:
            where.append(EntityMatchTable.dataset_id == request.dataset_id)
        if request.status:
            where.append(EntityMatchTable.status == request.status)
        if request.min_similarity is not None:
            where.append(EntityMatchTable.similarity_score >= request.min_similarity)

        count_result = await self.session.execute(select(func.count(EntityMatchTable.id)).where(*where))
        total = count_result.scalar_one()

        sort_column = {
            EntityMatchSortField.DATE_CREATED: EntityMatchTable.date_created,
            EntityMatchSortField.SIMILARITY_SCORE: EntityMatchTable.similarity_score,
        }[request.sort_by]
        order = desc(sort_column) if request.sort_order == SortOrder.DESC else asc(sort_column)

        stmt = (
            select(EntityMatchTable)
            .where(*where)
            .order_by(order)
            .offset((request.page - 1) * request.limit)
            .limit(request.limit)
        )
        result = await self.session.execute(stmt)
        data = [EntityMatch.model_validate(m) for m in result.scalars().all()]
        return PaginatedEntityMatchesResponse(
            total=total, page=request.page, limit=request.limit, data=data
        )

    async def resolve_match(self, match_id: str, review: EntityMatchReview) -> EntityMatch | None:
        """Record a decision on a candidate resolution.

        On confirm: attach the mention to the canonical entity, merge a
        provisional entity into it if one was set, and reject other pending
        candidates for the same mention.
        """
        stmt = (
            update(EntityMatchTable)
            .where(EntityMatchTable.id == match_id)
            .values(
                status=review.status,
                reviewed_by=review.reviewed_by,
                reviewed_at=datetime.now(UTC),
                review_note=review.review_note,
            )
            .returning(EntityMatchTable)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            await self.session.commit()
            return None

        if review.status == EntityMatchStatus.CONFIRMED:
            if row.mention_id:
                await self.session.execute(
                    update(MentionTable)
                    .where(MentionTable.id == row.mention_id)
                    .values(entity_id=row.entity_id)
                )
                await self.session.execute(
                    update(EntityMatchTable)
                    .where(
                        EntityMatchTable.mention_id == row.mention_id,
                        EntityMatchTable.id != match_id,
                        EntityMatchTable.status == EntityMatchStatus.PENDING,
                    )
                    .values(status=EntityMatchStatus.REJECTED)
                )
            if row.provisional_entity_id and row.provisional_entity_id != row.entity_id:
                await self._merge(canonical_id=row.entity_id, provisional_id=row.provisional_entity_id)

        match = EntityMatch.model_validate(row)
        await self.session.commit()
        return match

    async def _merge(self, *, canonical_id: str, provisional_id: str) -> None:
        await self.session.execute(
            update(MentionTable)
            .where(MentionTable.entity_id == provisional_id)
            .values(entity_id=canonical_id)
        )
        await self.session.execute(
            update(EntityRelationshipTable)
            .where(EntityRelationshipTable.src_entity_id == provisional_id)
            .values(src_entity_id=canonical_id)
        )
        await self.session.execute(
            update(EntityRelationshipTable)
            .where(EntityRelationshipTable.dst_entity_id == provisional_id)
            .values(dst_entity_id=canonical_id)
        )
        await self.session.execute(delete(EntityTable).where(EntityTable.id == provisional_id))

    async def delete_by_dataset_id(self, dataset_id: str) -> int:
        """Delete all candidate resolutions for a dataset (used by reset-entities)."""
        result = await self.session.execute(
            delete(EntityMatchTable).where(EntityMatchTable.dataset_id == dataset_id)
        )
        await self.session.commit()
        return result.rowcount or 0
