from datetime import UTC, datetime

from sqlalchemy import asc, delete, desc, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.entity_relationship_candidate import (
    EntityRelationshipCandidateTable,
)
from cipher.schemas.entity_relationship import (
    EntityRelationshipCreate,
    PaginatedRelationshipCandidatesResponse,
    RelationshipCandidate,
    RelationshipCandidateCreate,
    RelationshipCandidateSearchParameters,
    RelationshipCandidateStatus,
    RelationshipReview,
)
from cipher.schemas.ontology import RelationshipSource


class PostgresRelationshipCandidateRepository:
    """Postgres datastore for proposed edges awaiting review."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the entity_relationship_candidate table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(EntityRelationshipCandidateTable.metadata.create_all)

    async def create_batch(self, candidates: list[RelationshipCandidateCreate]) -> int:
        """Bulk-propose candidate edges, ignoring any already proposed."""
        if not candidates:
            return 0
        stmt = (
            pg_insert(EntityRelationshipCandidateTable)
            .values([c.model_dump(by_alias=False) for c in candidates])
            .on_conflict_do_nothing(constraint="uq_entity_relationship_candidate_triple")
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return len(candidates)

    async def get_by_id(self, candidate_id: str) -> RelationshipCandidate | None:
        """Retrieve a candidate edge by ID."""
        result = await self.session.execute(
            select(EntityRelationshipCandidateTable).where(
                EntityRelationshipCandidateTable.id == candidate_id
            )
        )
        row = result.scalar_one_or_none()
        return RelationshipCandidate.model_validate(row) if row else None

    async def list_candidates(
        self, request: RelationshipCandidateSearchParameters
    ) -> PaginatedRelationshipCandidatesResponse:
        """Query the relationship review queue."""
        where = []
        if request.src_entity_id:
            where.append(EntityRelationshipCandidateTable.src_entity_id == request.src_entity_id)
        if request.dst_entity_id:
            where.append(EntityRelationshipCandidateTable.dst_entity_id == request.dst_entity_id)
        if request.dataset_id:
            where.append(EntityRelationshipCandidateTable.dataset_id == request.dataset_id)
        if request.status:
            where.append(EntityRelationshipCandidateTable.status == request.status)

        count_result = await self.session.execute(
            select(func.count(EntityRelationshipCandidateTable.id)).where(*where)
        )
        total = count_result.scalar_one()

        order = (
            desc(EntityRelationshipCandidateTable.confidence)
            if request.sort_order.value == "desc"
            else asc(EntityRelationshipCandidateTable.confidence)
        )
        stmt = (
            select(EntityRelationshipCandidateTable)
            .where(*where)
            .order_by(order)
            .offset((request.page - 1) * request.limit)
            .limit(request.limit)
        )
        result = await self.session.execute(stmt)
        data = [RelationshipCandidate.model_validate(r) for r in result.scalars().all()]
        return PaginatedRelationshipCandidatesResponse(
            total=total, page=request.page, limit=request.limit, data=data
        )

    async def resolve(self, candidate_id: str, review: RelationshipReview) -> RelationshipCandidate | None:
        """Record a decision; on confirm, promote the candidate into `entity_relationship`."""
        stmt = (
            update(EntityRelationshipCandidateTable)
            .where(EntityRelationshipCandidateTable.id == candidate_id)
            .values(
                status=review.status,
                reviewed_by=review.reviewed_by,
                reviewed_at=datetime.now(UTC),
                review_note=review.review_note,
            )
            .returning(EntityRelationshipCandidateTable)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            await self.session.commit()
            return None

        if review.status == RelationshipCandidateStatus.CONFIRMED:
            edge = EntityRelationshipCreate(
                dataset_id=row.dataset_id,
                src_entity_id=row.src_entity_id,
                dst_entity_id=row.dst_entity_id,
                relationship_type=row.relationship_type,
                source=RelationshipSource.EXTRACTION,
                weight=row.confidence,
            )
            insert_stmt = pg_insert(EntityRelationshipTable).values(**edge.model_dump(by_alias=False))
            await self.session.execute(
                insert_stmt.on_conflict_do_update(
                    constraint="uq_entity_relationship_triple",
                    set_={"weight": insert_stmt.excluded.weight, "source": insert_stmt.excluded.source},
                )
            )

        candidate = RelationshipCandidate.model_validate(row)
        await self.session.commit()
        return candidate

    async def delete_by_dataset_id(self, dataset_id: str) -> int:
        """Delete all candidate edges for a dataset (used by reset-entities)."""
        result = await self.session.execute(
            delete(EntityRelationshipCandidateTable).where(
                EntityRelationshipCandidateTable.dataset_id == dataset_id
            )
        )
        await self.session.commit()
        return result.rowcount or 0
