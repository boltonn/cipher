from sqlalchemy import Float, asc, cast, delete, desc, exists, func, literal, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, defer

from cipher.datastores.postgres.tables.face import FaceTable
from cipher.datastores.postgres.tables.face_match import FaceMatchTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.image import ImageTable
from cipher.datastores.postgres.tables.person import PersonTable
from cipher.schemas.common import SortOrder, UriResponse
from cipher.schemas.exceptions import ValidationError
from cipher.schemas.face import (
    DEFAULT_FACE_MATCH_SIMILARITY,
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
    FaceStatus,
    PaginatedFaceSimilarityResponse,
    PaginatedFacesResponse,
)
from cipher.schemas.face_match import FaceMatchStatus

MAX_REPRESENTATIVE_FACES_PER_PERSON = 10


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
        stmt = self._joined_for_public(select(FaceTable)).options(defer(FaceTable.embedding))
        result = await self.session.execute(stmt.where(FaceTable.image_id == image_id))
        return [self._to_face_public(*row) for row in result.all()]

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

    async def get_face_uri(self, face_id: str) -> UriResponse | None:
        """Retrieve the URI of the source image a face was detected in."""
        stmt = (
            select(FileTable.uri, FileTable.mime_type)
            .select_from(FaceTable)
            .join(ImageTable, FaceTable.image_id == ImageTable.id)
            .join(FileTable, ImageTable.id == FileTable.sha256)
            .where(FaceTable.id == face_id)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        row = result.one_or_none()
        if row:
            uri, mime_type = row
            return UriResponse(uri=uri, mime_type=mime_type)
        return None

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
        face_table = result.scalar_one_or_none()
        # Validate to the Pydantic model before commit() expires face_table's
        # attributes -- reading them afterward would trigger a lazy load,
        # which fails outside an awaited context (MissingGreenlet).
        face = Face.model_validate(face_table) if face_table else None
        await self.session.commit()
        return face

    async def get_representative_faces(self, person_id: str) -> list[FacePublic]:
        """Retrieve a person's representative faces, primary face first (excludes embeddings)."""
        stmt = (
            self._joined_for_public(select(FaceTable))
            .options(defer(FaceTable.embedding))
            .where(FaceTable.person_id == person_id, FaceTable.is_representative.is_(True))
            .order_by(desc(FaceTable.is_primary))
        )
        result = await self.session.execute(stmt)
        return [self._to_face_public(*row) for row in result.all()]

    async def set_representative(self, face_id: str, data: FaceRepresentativeUpdate) -> Face | None:
        """Mark or unmark a face as representative (or primary) for its person.

        A face must already be assigned to a person. Setting `is_primary`
        clears any other primary face for that person first, since only
        one face per person may be primary. Newly marking a face
        representative is capped at `MAX_REPRESENTATIVE_FACES_PER_PERSON`
        per person.
        """
        face = await self.get_face_by_id(face_id)
        if face is None or face.person_id is None:
            return None

        is_representative = data.is_representative or data.is_primary
        is_primary = data.is_primary

        if is_representative and not face.is_representative:
            count_result = await self.session.execute(
                select(func.count(FaceTable.id)).where(
                    FaceTable.person_id == face.person_id,
                    FaceTable.is_representative.is_(True),
                )
            )
            if count_result.scalar_one() >= MAX_REPRESENTATIVE_FACES_PER_PERSON:
                raise ValidationError(
                    field="is_representative",
                    reason=f"a person can have at most {MAX_REPRESENTATIVE_FACES_PER_PERSON} representative faces",
                )

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
        face_table = result.scalar_one_or_none()
        face = Face.model_validate(face_table) if face_table else None
        await self.session.commit()
        return face

    async def delete_face(self, face_id: str) -> bool:
        """Delete a face by ID."""
        result = await self.session.execute(delete(FaceTable).where(FaceTable.id == face_id))
        await self.session.commit()
        return bool(result.rowcount)

    @staticmethod
    def _to_face_public(
        face: FaceTable,
        uri: str,
        is_verified: bool | None,
        candidate_person_id: str | None,
        candidate_person_name: str | None,
    ) -> FacePublic:
        """Build a FacePublic from a Face row plus its joined file uri and status inputs."""
        if face.person_id and is_verified:
            status = FaceStatus.VERIFIED
        elif face.person_id or candidate_person_id:
            status = FaceStatus.MATCHED
        else:
            status = FaceStatus.UNMATCHED
        return FacePublic.model_validate({
            **face.__dict__,
            "uri": uri,
            "status": status,
            # the candidate is only meaningful when not already assigned
            "candidate_person_id": candidate_person_id if not face.person_id else None,
            "candidate_person_name": candidate_person_name if not face.person_id else None,
        })

    def _joined_for_public(self, stmt):
        """Join everything `_to_face_public` needs onto a Face select.

        Adds `(uri, is_verified, candidate_person_id, candidate_person_name)` columns.
        Joins through Image->File (display uri), Person (assignment
        verification), and each face's single best still-pending FaceMatch
        candidate (for the "matched but not yet confirmed" status and its
        candidate name).

        `file_repr` picks exactly one file per image content (sha256) --
        `Image` no longer has a single owning file (it's shared by every file
        with identical content), so joining `FileTable` directly would fan
        out one Face row into one row per file sharing that content.
        """
        file_repr = (
            select(FileTable.sha256, FileTable.uri, FileTable.mime_type)
            .distinct(FileTable.sha256)
            .order_by(FileTable.sha256, FileTable.id)
            .subquery()
        )
        top_match = (
            select(FaceMatchTable.face_id.label("face_id"), FaceMatchTable.person_id.label("person_id"))
            .where(FaceMatchTable.status == FaceMatchStatus.PENDING)
            .order_by(FaceMatchTable.face_id, desc(FaceMatchTable.similarity_score))
            .distinct(FaceMatchTable.face_id)
            .subquery()
        )
        candidate_person = aliased(PersonTable)
        return (
            stmt.join(ImageTable, FaceTable.image_id == ImageTable.id)
            .join(file_repr, file_repr.c.sha256 == ImageTable.id)
            .outerjoin(PersonTable, FaceTable.person_id == PersonTable.id)
            .outerjoin(top_match, top_match.c.face_id == FaceTable.id)
            .outerjoin(candidate_person, top_match.c.person_id == candidate_person.id)
            .add_columns(file_repr.c.uri, PersonTable.is_verified, candidate_person.id, candidate_person.name)
        )

    @staticmethod
    def _min_face_size_expr():
        """Pixel size of the bounding box's shorter side, using the source image's resolution.

        The bounding box is stored normalized (0-1) in JSONB; multiplying by
        the joined image's own width/height converts it to actual pixels.
        """
        width_px = cast(FaceTable.bounding_box["width"].astext, Float) * ImageTable.width
        height_px = cast(FaceTable.bounding_box["height"].astext, Float) * ImageTable.height
        return func.least(width_px, height_px)

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
        if request.min_size is not None:
            filters.append(self._min_face_size_expr() >= request.min_size)
        if request.person_ids:
            filters.append(
                or_(
                    FaceTable.person_id.in_(request.person_ids),
                    exists(
                        select(literal(1))
                        .select_from(FaceMatchTable)
                        .where(
                            FaceMatchTable.face_id == FaceTable.id,
                            FaceMatchTable.status == FaceMatchStatus.PENDING,
                            FaceMatchTable.person_id.in_(request.person_ids),
                        )
                    ),
                )
            )
        return filters

    async def search_faces(self, request: BaseFaceSearchParameters) -> PaginatedFacesResponse:
        """Query faces with filtering, pagination, and sorting."""
        filters = self._filters(request)

        count_result = await self.session.execute(
            select(func.count(FaceTable.id))
            .select_from(FaceTable)
            .join(ImageTable, FaceTable.image_id == ImageTable.id)
            .where(*filters)
        )
        total_count = count_result.scalar_one()

        sort_column = {
            FaceSortField.DATE_CREATED: FaceTable.date_created,
            FaceSortField.QUALITY: FaceTable.quality_score,
            FaceSortField.DETECTION_CONFIDENCE: FaceTable.detection_confidence,
        }.get(request.sort_by, FaceTable.date_created)

        data_stmt = (
            self._joined_for_public(select(FaceTable))
            .options(defer(FaceTable.embedding))
            .where(*filters)
            .order_by(desc(sort_column) if request.sort_order == SortOrder.DESC else asc(sort_column))
            .offset((request.page - 1) * request.limit)
            .limit(request.limit)
        )

        result = await self.session.execute(data_stmt)
        faces = [self._to_face_public(*row) for row in result.all()]

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

        count_result = await self.session.execute(
            select(func.count(FaceTable.id))
            .select_from(FaceTable)
            .join(ImageTable, FaceTable.image_id == ImageTable.id)
            .where(*filters)
        )
        total_count = count_result.scalar_one()

        stmt = (
            self._joined_for_public(select(FaceTable, (-distance_expr).label("similarity_score")))
            .options(defer(FaceTable.embedding))
            .where(*filters)
            .order_by(asc(distance_expr))
            .offset((request.page - 1) * request.limit)
            .limit(request.limit)
        )

        result = await self.session.execute(stmt)
        rows = list(result.all())

        faces = [
            FaceSimilarityResult(
                **self._to_face_public(
                    face, uri, is_verified, candidate_person_id, candidate_person_name
                ).model_dump(),
                # Similarity is surfaced as a 0-1 "match strength", not a raw
                # signed cosine value: floor negative cosine similarity to 0,
                # and cap float32 rounding overshoot (e.g. 1.0000001192...) to 1.
                similarity_score=max(0.0, min(1.0, similarity_score)),
            )
            for face, similarity_score, uri, is_verified, candidate_person_id, candidate_person_name in rows
        ]

        return PaginatedFaceSimilarityResponse(
            total=total_count,
            page=request.page,
            limit=request.limit,
            data=faces,
        )

    async def get_potential_person_matches(
        self,
        face_id: str,
        min_similarity: float = DEFAULT_FACE_MATCH_SIMILARITY,
        limit: int = 20,
    ) -> list[FaceSimilarityResult]:
        """KNN-search for still-unassigned faces similar to `face_id`.

        The one definition of "a potential match" for a face -- proposing
        candidates for analyst review (via `FaceMatch`) after a person gains a
        new reference face, and any future ingestion-time matcher, should both
        call this rather than each constructing their own KNN query.
        """
        request = FaceIdKnnSearchRequest(
            face_id=face_id,
            unassigned_only=True,
            min_similarity=min_similarity,
            limit=limit,
        )
        response = await self.search_similar_faces(request=request)
        return response.data
