from sqlalchemy import asc, delete, desc, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from cipher.datastores.postgres.tables.face import FaceTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.image import ImageTable
from cipher.schemas.common import SortOrder
from cipher.schemas.face import (
    BaseFaceSearchParameters,
    Face,
    FaceAssignment,
    FaceCreate,
    FaceIdKnnSearchRequest,
    FacePublic,
    FaceRepresentativeUpdate,
    FaceSimilarityResult,
    FaceSimilaritySearchRequest,
    FaceSortField,
    PaginatedFaceSimilarityResponse,
    PaginatedFacesResponse,
)


class PostgresFaceRepository:
    """Postgres datastore implementation for faces using SQLAlchemy."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the face table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(FaceTable.metadata.create_all)
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    async def create_vector_index(self, m: int = 16, ef_construction: int = 64):
        """Manually create the HNSW index for face embedding search."""
        sql = text(f"""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS hnsw_idx_face_embedding
            ON face USING hnsw (embedding vector_ip_ops)
            WITH (m = {m}, ef_construction = {ef_construction});
        """)
        async with self.session.bind.begin() as conn:
            await conn.execute(sql)
            await conn.commit()

    async def get_count(self) -> int:
        """Get total count of faces."""
        result = await self.session.execute(select(func.count(FaceTable.id)))
        return result.scalar_one()

    async def add_face(self, face: FaceCreate) -> Face:
        """Add a single detected face."""
        face_table = FaceTable(**face.model_dump())
        self.session.add(face_table)
        await self.session.commit()
        await self.session.refresh(face_table)
        return Face.model_validate(face_table)

    async def add_faces_batch(self, faces: list[FaceCreate]) -> None:
        """Bulk insert detected faces, e.g. from a face detection job."""
        if not faces:
            return
        self.session.add_all([FaceTable(**f.model_dump()) for f in faces])
        await self.session.commit()

    async def get_face_by_id(self, face_id: str) -> Face | None:
        """Retrieve a face by ID."""
        result = await self.session.execute(select(FaceTable).where(FaceTable.id == face_id))
        face_table = result.scalar_one_or_none()
        return Face.model_validate(face_table) if face_table else None

    async def get_faces_by_image(self, image_id: str) -> list[FacePublic]:
        """Retrieve all faces detected in an image (excludes embeddings)."""
        stmt = self._joined_to_file(select(FaceTable, FileTable.uri)).options(defer(FaceTable.embedding))
        result = await self.session.execute(stmt.where(FaceTable.image_id == image_id))
        return [self._to_face_public(face, uri) for face, uri in result.all()]

    async def get_faces_with_embeddings_by_image(self, image_id: str) -> list[Face]:
        """Retrieve all faces for an image, embeddings included.

        Used to clone detection results onto a duplicate image (same
        content, different file) instead of re-running detection.
        """
        result = await self.session.execute(select(FaceTable).where(FaceTable.image_id == image_id))
        return [Face.model_validate(f) for f in result.scalars().all()]

    async def get_embedding_by_face_id(self, face_id: str) -> list[float] | None:
        """Retrieve the embedding vector for a face."""
        result = await self.session.execute(select(FaceTable.embedding).where(FaceTable.id == face_id))
        return result.scalar_one_or_none()

    async def assign_person(self, face_id: str, assignment: FaceAssignment) -> Face | None:
        """Link (or unlink) a face to a person.

        Reassigning always clears representative/primary status, since
        that curation is specific to the previously assigned person and
        must be re-applied deliberately via `set_representative`.
        """
        stmt = (
            update(FaceTable)
            .where(FaceTable.id == face_id)
            .values(
                person_id=assignment.person_id,
                assignment_method=assignment.assignment_method if assignment.person_id else None,
                assignment_confidence=assignment.assignment_confidence if assignment.person_id else None,
                is_representative=False,
                is_primary=False,
            )
            .returning(FaceTable)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        face_table = result.scalar_one_or_none()
        return Face.model_validate(face_table) if face_table else None

    async def get_representative_faces(self, person_id: str) -> list[FacePublic]:
        """Retrieve a person's representative faces, primary face first (excludes embeddings)."""
        stmt = (
            self._joined_to_file(select(FaceTable, FileTable.uri))
            .options(defer(FaceTable.embedding))
            .where(FaceTable.person_id == person_id, FaceTable.is_representative.is_(True))
            .order_by(desc(FaceTable.is_primary))
        )
        result = await self.session.execute(stmt)
        return [self._to_face_public(face, uri) for face, uri in result.all()]

    async def set_representative(self, face_id: str, data: FaceRepresentativeUpdate) -> Face | None:
        """Mark or unmark a face as representative (or primary) for its person.

        A face must already be assigned to a person. Setting `is_primary`
        clears any other primary face for that person first, since only
        one face per person may be primary.
        """
        face = await self.get_face_by_id(face_id)
        if face is None or face.person_id is None:
            return None

        is_representative = data.is_representative or data.is_primary
        is_primary = data.is_primary

        if is_primary:
            await self.session.execute(
                update(FaceTable)
                .where(
                    FaceTable.person_id == face.person_id,
                    FaceTable.id != face_id,
                    FaceTable.is_primary.is_(True),
                )
                .values(is_primary=False)
            )

        stmt = (
            update(FaceTable)
            .where(FaceTable.id == face_id)
            .values(is_representative=is_representative, is_primary=is_primary)
            .returning(FaceTable)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        face_table = result.scalar_one_or_none()
        return Face.model_validate(face_table) if face_table else None

    async def delete_face(self, face_id: str) -> bool:
        """Delete a face by ID."""
        result = await self.session.execute(delete(FaceTable).where(FaceTable.id == face_id))
        await self.session.commit()
        return bool(result.rowcount)

    @staticmethod
    def _to_face_public(face: FaceTable, uri: str) -> FacePublic:
        """Build a FacePublic from a Face row plus its joined file uri."""
        return FacePublic.model_validate({**face.__dict__, "uri": uri})

    def _joined_to_file(self, stmt):
        """Join a Face select through Image to File, for its display uri."""
        return stmt.join(ImageTable, FaceTable.image_id == ImageTable.id).join(
            FileTable, ImageTable.file_id == FileTable.id
        )

    def _filters(self, request: BaseFaceSearchParameters) -> list:
        filters = []
        if request.image_id:
            filters.append(FaceTable.image_id == request.image_id)
        if request.person_id:
            filters.append(FaceTable.person_id == request.person_id)
        if request.unassigned_only:
            filters.append(FaceTable.person_id.is_(None))
        if request.representative_only:
            filters.append(FaceTable.is_representative.is_(True))
        if request.min_quality is not None:
            filters.append(FaceTable.quality_score >= request.min_quality)
        return filters

    async def search_faces(self, request: BaseFaceSearchParameters) -> PaginatedFacesResponse:
        """Query faces with filtering, pagination, and sorting."""
        filters = self._filters(request)

        count_result = await self.session.execute(select(func.count(FaceTable.id)).where(*filters))
        total_count = count_result.scalar_one()

        sort_column = {
            FaceSortField.DATE_CREATED: FaceTable.date_created,
            FaceSortField.QUALITY: FaceTable.quality_score,
            FaceSortField.DETECTION_CONFIDENCE: FaceTable.detection_confidence,
        }.get(request.sort_by, FaceTable.date_created)

        data_stmt = (
            self._joined_to_file(select(FaceTable, FileTable.uri))
            .options(defer(FaceTable.embedding))
            .where(*filters)
            .order_by(desc(sort_column) if request.sort_order == SortOrder.DESC else asc(sort_column))
            .offset((request.page - 1) * request.limit)
            .limit(request.limit)
        )

        result = await self.session.execute(data_stmt)
        faces = [self._to_face_public(face, uri) for face, uri in result.all()]

        return PaginatedFacesResponse(
            total=total_count,
            page=request.page,
            limit=request.limit,
            data=faces,
        )

    async def search_similar_faces(
        self, request: FaceSimilaritySearchRequest | FaceIdKnnSearchRequest
    ) -> PaginatedFaceSimilarityResponse:
        """Find faces by KNN similarity search using inner product.

        Accepts either a raw embedding or the ID of an existing face to
        search from (e.g. when proposing clusters of faces that may share
        an unassigned identity).
        """
        if isinstance(request, FaceIdKnnSearchRequest):
            embedding = await self.get_embedding_by_face_id(request.face_id)
            if embedding is None:
                return PaginatedFaceSimilarityResponse(total=0, page=1, limit=request.limit, data=[])
            exclude_face_id = request.face_id
        else:
            embedding = request.embedding
            exclude_face_id = None

        distance_expr = FaceTable.embedding.max_inner_product(embedding)

        filters = self._filters(request)
        if exclude_face_id:
            filters.append(FaceTable.id != exclude_face_id)
        if request.min_similarity is not None:
            filters.append(distance_expr <= -request.min_similarity)

        stmt = (
            self._joined_to_file(select(FaceTable, FileTable.uri, (-distance_expr).label("similarity_score")))
            .options(defer(FaceTable.embedding))
            .where(*filters)
            .order_by(asc(distance_expr))
            .limit(request.limit)
        )

        result = await self.session.execute(stmt)
        rows = list(result.all())

        faces = [
            FaceSimilarityResult(
                **self._to_face_public(face, uri).model_dump(),
                similarity_score=similarity_score,
            )
            for face, uri, similarity_score in rows
        ]

        return PaginatedFaceSimilarityResponse(
            total=len(faces),
            page=1,
            limit=request.limit,
            data=faces,
        )
