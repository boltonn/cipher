from datetime import UTC, datetime

from sqlalchemy import asc, delete, desc, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.face import FaceTable
from cipher.datastores.postgres.tables.face_match import FaceMatchTable
from cipher.schemas.common import SortOrder
from cipher.schemas.face import FaceAssignmentMethod
from cipher.schemas.face_match import (
    FaceMatch,
    FaceMatchCreate,
    FaceMatchReview,
    FaceMatchSearchParameters,
    FaceMatchSortField,
    FaceMatchStatus,
    PaginatedFaceMatchesResponse,
)


class PostgresFaceMatchRepository:
    """Postgres datastore implementation for candidate face-to-person matches."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the face_match table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(FaceMatchTable.metadata.create_all)

    async def get_count(self) -> int:
        """Get total count of face matches."""
        result = await self.session.execute(select(func.count(FaceMatchTable.id)))
        return result.scalar_one()

    async def create_match(self, match: FaceMatchCreate) -> FaceMatch:
        """Create a candidate match, returning the existing row if already proposed."""
        stmt = (
            pg_insert(FaceMatchTable)
            .values(**match.model_dump())
            .on_conflict_do_nothing(constraint="uq_face_match_face_person")
            .returning(FaceMatchTable)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()

        match_table = result.scalar_one_or_none()
        if match_table:
            return FaceMatch.model_validate(match_table)

        existing = await self.session.execute(
            select(FaceMatchTable).where(
                FaceMatchTable.face_id == match.face_id,
                FaceMatchTable.person_id == match.person_id,
            )
        )
        return FaceMatch.model_validate(existing.scalar_one())

    async def create_matches_batch(self, matches: list[FaceMatchCreate]) -> None:
        """Bulk propose candidate matches, e.g. from a matching job."""
        if not matches:
            return
        stmt = (
            pg_insert(FaceMatchTable)
            .values([m.model_dump() for m in matches])
            .on_conflict_do_nothing(constraint="uq_face_match_face_person")
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_match_by_id(self, match_id: str) -> FaceMatch | None:
        """Retrieve a candidate match by ID."""
        result = await self.session.execute(select(FaceMatchTable).where(FaceMatchTable.id == match_id))
        match_table = result.scalar_one_or_none()
        return FaceMatch.model_validate(match_table) if match_table else None

    async def list_matches(self, request: FaceMatchSearchParameters) -> PaginatedFaceMatchesResponse:
        """Query candidate matches with filtering, pagination, and sorting."""
        filters = []
        if request.face_id:
            filters.append(FaceMatchTable.face_id == request.face_id)
        if request.person_id:
            filters.append(FaceMatchTable.person_id == request.person_id)
        if request.status:
            filters.append(FaceMatchTable.status == request.status)
        if request.min_similarity is not None:
            filters.append(FaceMatchTable.similarity_score >= request.min_similarity)

        count_result = await self.session.execute(select(func.count(FaceMatchTable.id)).where(*filters))
        total_count = count_result.scalar_one()

        sort_column = {
            FaceMatchSortField.DATE_CREATED: FaceMatchTable.date_created,
            FaceMatchSortField.SIMILARITY_SCORE: FaceMatchTable.similarity_score,
        }.get(request.sort_by, FaceMatchTable.similarity_score)

        data_stmt = (
            select(FaceMatchTable)
            .where(*filters)
            .order_by(desc(sort_column) if request.sort_order == SortOrder.DESC else asc(sort_column))
            .offset((request.page - 1) * request.limit)
            .limit(request.limit)
        )

        result = await self.session.execute(data_stmt)
        matches = [FaceMatch.model_validate(m) for m in result.scalars().all()]

        return PaginatedFaceMatchesResponse(
            total=total_count,
            page=request.page,
            limit=request.limit,
            data=matches,
        )

    async def resolve_match(self, match_id: str, review: FaceMatchReview) -> FaceMatch | None:
        """Record an analyst's decision on a candidate match.

        Confirming a match assigns the face to the person and rejects any
        other pending candidates proposed for that same face, since a face
        can only belong to one person.
        """
        stmt = (
            update(FaceMatchTable)
            .where(FaceMatchTable.id == match_id)
            .values(
                status=review.status,
                reviewed_by=review.reviewed_by,
                reviewed_at=datetime.now(UTC),
                review_note=review.review_note,
            )
            .returning(FaceMatchTable)
        )
        result = await self.session.execute(stmt)
        match_table = result.scalar_one_or_none()
        if not match_table:
            await self.session.commit()
            return None

        if review.status == FaceMatchStatus.CONFIRMED:
            await self.session.execute(
                update(FaceTable)
                .where(FaceTable.id == match_table.face_id)
                .values(
                    person_id=match_table.person_id,
                    assignment_method=FaceAssignmentMethod.MANUAL,
                    assignment_confidence=match_table.similarity_score,
                )
            )
            await self.session.execute(
                update(FaceMatchTable)
                .where(
                    FaceMatchTable.face_id == match_table.face_id,
                    FaceMatchTable.id != match_id,
                    FaceMatchTable.status == FaceMatchStatus.PENDING,
                )
                .values(status=FaceMatchStatus.REJECTED)
            )

        await self.session.commit()
        await self.session.refresh(match_table)
        return FaceMatch.model_validate(match_table)

    async def delete_match(self, match_id: str) -> bool:
        """Delete a candidate match by ID."""
        result = await self.session.execute(delete(FaceMatchTable).where(FaceMatchTable.id == match_id))
        await self.session.commit()
        return bool(result.rowcount)
