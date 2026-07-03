from sqlalchemy import asc, delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.face import FaceTable
from cipher.datastores.postgres.tables.person import PersonTable
from cipher.schemas.common import SortOrder
from cipher.schemas.person import (
    PaginatedPersonSimilarityResponse,
    PaginatedPersonsResponse,
    Person,
    PersonCreate,
    PersonSearchParameters,
    PersonSimilarityResult,
    PersonSimilaritySearchRequest,
    PersonSortField,
    PersonUpdate,
)


class PostgresPersonRepository:
    """Postgres datastore implementation for persons using SQLAlchemy."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the person table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(PersonTable.metadata.create_all)

    async def get_count(self) -> int:
        """Get total count of persons."""
        result = await self.session.execute(select(func.count(PersonTable.id)))
        return result.scalar_one()

    async def add_person(self, person: PersonCreate) -> Person:
        """Create a new person."""
        person_table = PersonTable(**person.model_dump())
        self.session.add(person_table)
        await self.session.commit()
        await self.session.refresh(person_table)
        return Person.model_validate(person_table)

    async def get_person_by_id(self, person_id: str) -> Person | None:
        """Retrieve a person by ID."""
        result = await self.session.execute(select(PersonTable).where(PersonTable.id == person_id))
        person_table = result.scalar_one_or_none()
        return Person.model_validate(person_table) if person_table else None

    async def update_person(self, person_id: str, data: PersonUpdate) -> Person | None:
        """Update a person by ID."""
        update_dict = data.model_dump(exclude_unset=True, by_alias=False)
        stmt = update(PersonTable).where(PersonTable.id == person_id).values(**update_dict).returning(PersonTable)
        result = await self.session.execute(stmt)
        await self.session.commit()
        person_table = result.scalar_one_or_none()
        return Person.model_validate(person_table) if person_table else None

    async def delete_person(self, person_id: str) -> bool:
        """Delete a person by ID."""
        result = await self.session.execute(delete(PersonTable).where(PersonTable.id == person_id))
        await self.session.commit()
        return bool(result.rowcount)

    async def search_persons(self, request: PersonSearchParameters) -> PaginatedPersonsResponse:
        """Query persons with filtering, pagination, and sorting."""
        where_clause = []
        if request.query:
            where_clause.append(
                or_(
                    PersonTable.name.ilike(f"%{request.query}%"),
                    PersonTable.notes.ilike(f"%{request.query}%"),
                )
            )
        if request.tags:
            where_clause.append(PersonTable.tags.overlap(request.tags))
        if request.is_verified is not None:
            where_clause.append(PersonTable.is_verified == request.is_verified)

        count_stmt = select(func.count(PersonTable.id))
        if where_clause:
            count_stmt = count_stmt.where(*where_clause)
        count_result = await self.session.execute(count_stmt)
        total_count = count_result.scalar_one()

        sort_column = {
            PersonSortField.NAME: PersonTable.name,
            PersonSortField.DATE_CREATED: PersonTable.date_created,
            PersonSortField.DATE_UPDATED: PersonTable.date_updated,
        }[request.sort_by]

        data_stmt = select(PersonTable)
        if where_clause:
            data_stmt = data_stmt.where(*where_clause)
        data_stmt = data_stmt.order_by(desc(sort_column) if request.sort_order == SortOrder.DESC else asc(sort_column))
        data_stmt = data_stmt.offset((request.page - 1) * request.limit).limit(request.limit)

        result = await self.session.execute(data_stmt)
        persons = [Person.model_validate(p) for p in result.scalars().all()]

        return PaginatedPersonsResponse(
            total=total_count,
            page=request.page,
            limit=request.limit,
            data=persons,
        )

    async def search_similar_persons(self, request: PersonSimilaritySearchRequest) -> PaginatedPersonSimilarityResponse:
        """Find candidate persons by KNN search against representative faces.

        A person has no single centroid embedding: they match if the query
        embedding is close to *any* of their representative faces. For each
        person we keep only their single best-matching representative face
        (via DISTINCT ON), then rank persons by that best match.
        """
        distance_expr = FaceTable.embedding.max_inner_product(request.embedding)

        best_face_per_person = (
            select(
                FaceTable.person_id.label("person_id"),
                FaceTable.id.label("face_id"),
                (-distance_expr).label("similarity_score"),
            )
            .where(
                FaceTable.is_representative.is_(True),
                FaceTable.person_id.is_not(None),
                FaceTable.embedding.is_not(None),
            )
            .distinct(FaceTable.person_id)
            .order_by(FaceTable.person_id, asc(distance_expr))
            .subquery()
        )

        stmt = select(
            PersonTable,
            best_face_per_person.c.face_id,
            best_face_per_person.c.similarity_score,
        ).join(best_face_per_person, PersonTable.id == best_face_per_person.c.person_id)
        if request.min_similarity is not None:
            stmt = stmt.where(best_face_per_person.c.similarity_score >= request.min_similarity)
        stmt = stmt.order_by(desc(best_face_per_person.c.similarity_score)).limit(request.limit)

        result = await self.session.execute(stmt)
        rows = list(result.all())

        persons = [
            PersonSimilarityResult(
                **Person.model_validate(person).model_dump(),
                similarity_score=similarity_score,
                matched_face_id=face_id,
            )
            for person, face_id, similarity_score in rows
        ]

        return PaginatedPersonSimilarityResponse(
            total=len(persons),
            page=1,
            limit=request.limit,
            data=persons,
        )
