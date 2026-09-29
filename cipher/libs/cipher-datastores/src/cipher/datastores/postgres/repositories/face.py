from datetime import UTC, datetime

from sqlalchemy import Float, asc, cast, delete, desc, exists, func, literal, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, defer

from cipher.datastores.postgres.tables.face import FaceTable
from cipher.datastores.postgres.tables.face_match import FaceMatchTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.image import ImageTable
from cipher.datastores.postgres.tables.person import PersonTable
from cipher.schemas._base.common import SortOrder, UriResponse
from cipher.schemas._base.exceptions import ValidationError
from cipher.schemas.identity.face import (
    DEFAULT_FACE_MATCH_SIMILARITY,
    DEFAULT_FACE_REJECT_SIMILARITY,
    BaseFaceSearchParameters,
    Face,
    FaceAssignment,
    FaceAssignmentMethod,
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
from cipher.schemas.identity.face_match import FaceMatchStatus

MAX_REPRESENTATIVE_FACES_PER_PERSON = 10
MAX_AUTO_REJECT_NEIGHBOURS = 1000


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

    async def image_has_faces(self, image_id: str) -> bool:
        """Whether any face row already exists for this image (content hash).

        Cheap guard for the detection pipeline: `image_id` is the sha256, so a
        hit means some file sharing this content has already been detected and
        re-running would only append duplicate rows.
        """
        return bool(await self.session.scalar(select(exists().where(FaceTable.image_id == image_id))))

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
                **(
                    dict(date_rejected=None, rejection_method=None, rejection_confidence=None)
                    if assignment.person_id
                    else {}
                ),
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

    async def image_ids_for_person(self, person_id: str) -> list[str]:
        """Distinct source-image ids of every face assigned to a person."""
        result = await self.session.execute(
            select(FaceTable.image_id).where(FaceTable.person_id == person_id).distinct()
        )
        return list(result.scalars().all())

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

    # --- Rejection ("not a face") -------------------------------------------
    #
    # Manually rejected faces double as negative exemplars: any unassigned face
    # close enough to one (another photo of the same cat) is auto-rejected,
    # flagged `automatic` with its similarity so an analyst can see why and undo.
    # Auto-rejected faces never act as exemplars themselves, so it can't drift.

    async def _reject_pending_matches(self, face_ids: list[str], reviewed_by: str | None) -> None:
        await self.session.execute(
            update(FaceMatchTable)
            .where(FaceMatchTable.face_id.in_(face_ids), FaceMatchTable.status == FaceMatchStatus.PENDING)
            .values(
                status=FaceMatchStatus.REJECTED,
                reviewed_by=reviewed_by,
                reviewed_at=datetime.now(UTC),
                review_note="not a face",
            )
        )

    async def reject_faces(self, face_ids: list[str], *, reviewed_by: str | None = None) -> int:
        """Mark faces not-a-face by hand: unassigns them and rejects their pending matches."""
        result = await self.session.execute(
            update(FaceTable)
            .where(FaceTable.id.in_(face_ids))
            .values(
                person_id=None,
                assignment_method=None,
                assignment_confidence=None,
                is_representative=False,
                is_primary=False,
                date_rejected=datetime.now(UTC),
                rejection_method=FaceAssignmentMethod.MANUAL,
                rejection_confidence=None,
            )
        )
        await self._reject_pending_matches(face_ids, reviewed_by)
        await self.session.commit()
        return result.rowcount or 0

    async def unreject_faces(
        self, face_ids: list[str], *, min_similarity: float = DEFAULT_FACE_REJECT_SIMILARITY
    ) -> int:
        """Clear not-a-face on these faces, then release auto-rejections nothing supports any more."""
        result = await self.session.execute(
            update(FaceTable)
            .where(FaceTable.id.in_(face_ids), FaceTable.date_rejected.is_not(None))
            .values(date_rejected=None, rejection_method=None, rejection_confidence=None)
        )
        await self.session.commit()
        return (result.rowcount or 0) + await self.release_unsupported_auto_rejections(min_similarity=min_similarity)

    @staticmethod
    def _manual_exemplars():
        return select(FaceTable.id.label("id"), FaceTable.embedding.label("embedding")).where(
            FaceTable.rejection_method == FaceAssignmentMethod.MANUAL,
            FaceTable.date_rejected.is_not(None),
            FaceTable.embedding.is_not(None),
        )

    async def release_unsupported_auto_rejections(
        self, *, min_similarity: float = DEFAULT_FACE_REJECT_SIMILARITY
    ) -> int:
        """Un-reject automatic rejections no longer within `min_similarity` of any manual exemplar."""
        exemplars = self._manual_exemplars().subquery("ex")
        supported = exists(
            select(literal(1)).where(-FaceTable.embedding.max_inner_product(exemplars.c.embedding) >= min_similarity)
        )
        result = await self.session.execute(
            update(FaceTable)
            .where(FaceTable.rejection_method == FaceAssignmentMethod.AUTOMATIC, ~supported)
            .values(date_rejected=None, rejection_method=None, rejection_confidence=None)
        )
        await self.session.commit()
        return result.rowcount or 0

    async def auto_reject_similar(
        self,
        *,
        exemplar_ids: list[str] | None = None,
        image_ids: list[str] | None = None,
        min_similarity: float = DEFAULT_FACE_REJECT_SIMILARITY,
    ) -> list[str]:
        """Auto-reject unassigned faces within `min_similarity` of a manually rejected face.

        `image_ids` checks just the faces in those images against every exemplar
        (brute force -- new detections vs. a small exemplar set). Otherwise each
        exemplar (`exemplar_ids`, or all of them) walks the HNSW index for its
        neighbours. Never touches assigned or already-rejected faces. Returns
        the ids of the faces rejected.
        """
        candidate_filters = [
            FaceTable.person_id.is_(None),
            FaceTable.date_rejected.is_(None),
            FaceTable.embedding.is_not(None),
        ]
        exemplar_q = self._manual_exemplars()
        if exemplar_ids is not None:
            exemplar_q = exemplar_q.where(FaceTable.id.in_(exemplar_ids))
        exemplars = exemplar_q.subquery("ex")

        if image_ids is not None:
            if not image_ids:
                return []
            sim = func.max(-FaceTable.embedding.max_inner_product(exemplars.c.embedding))
            stmt = (
                select(FaceTable.id, sim)
                .select_from(FaceTable)
                .join(exemplars, literal(True))
                .where(*candidate_filters, FaceTable.image_id.in_(image_ids))
                .group_by(FaceTable.id)
                .having(sim >= min_similarity)
            )
        else:
            await self.session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
            distance = FaceTable.embedding.max_inner_product(exemplars.c.embedding)
            neighbours = (
                select(FaceTable.id.label("id"), (-distance).label("sim"))
                .where(*candidate_filters, distance <= -min_similarity)
                .order_by(asc(distance))
                .limit(MAX_AUTO_REJECT_NEIGHBOURS)
                .lateral("nn")
            )
            stmt = (
                select(neighbours.c.id, func.max(neighbours.c.sim))
                .select_from(exemplars)
                .join(neighbours, literal(True))
                .group_by(neighbours.c.id)
            )

        hits = (await self.session.execute(stmt)).all()
        if not hits:
            return []
        now = datetime.now(UTC)
        await self.session.execute(
            update(FaceTable),
            [
                {
                    "id": face_id,
                    "date_rejected": now,
                    "rejection_method": FaceAssignmentMethod.AUTOMATIC,
                    "rejection_confidence": max(0.0, min(1.0, float(similarity))),
                }
                for face_id, similarity in hits
            ],
        )
        rejected_ids = [face_id for face_id, _ in hits]
        await self._reject_pending_matches(rejected_ids, reviewed_by=None)
        await self.session.commit()
        return rejected_ids

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
        person_name: str | None,
        candidate_person_id: str | None,
        candidate_person_name: str | None,
    ) -> FacePublic:
        """Build a FacePublic from a Face row plus its joined file uri and status inputs."""
        if face.date_rejected:
            status = FaceStatus.REJECTED
        elif face.person_id and is_verified:
            status = FaceStatus.VERIFIED
        elif face.person_id or candidate_person_id:
            status = FaceStatus.MATCHED
        else:
            status = FaceStatus.UNMATCHED
        return FacePublic.model_validate(
            {
                **face.__dict__,
                "uri": uri,
                "status": status,
                # assigned person's name, denormalized so a grid of cards needn't
                # fetch it per card
                "person_name": person_name if face.person_id else None,
                # the candidate is only meaningful when not already assigned
                "candidate_person_id": candidate_person_id if not face.person_id else None,
                "candidate_person_name": candidate_person_name if not face.person_id else None,
            }
        )

    def _joined_for_public(self, stmt):
        """Join everything `_to_face_public` needs onto a Face select.

        Adds `(uri, is_verified, person_name, candidate_person_id, candidate_person_name)` columns.
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
            .add_columns(
                file_repr.c.uri,
                PersonTable.is_verified,
                PersonTable.name,
                candidate_person.id,
                candidate_person.name,
            )
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
        filters = [FaceTable.date_rejected.is_not(None) if request.rejected_only else FaceTable.date_rejected.is_(None)]
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

        return PaginatedFaceSimilarityResponse(
            total=total_count,
            page=request.page,
            limit=request.limit,
            data=[self._row_to_similarity_result(row) for row in rows],
        )

    @staticmethod
    def _row_to_similarity_result(row) -> FaceSimilarityResult:
        """Map a `(FaceTable, similarity, *public-status cols)` row to a result model."""
        face, similarity_score, uri, is_verified, person_name, candidate_person_id, candidate_person_name = row
        return FaceSimilarityResult(
            **PostgresFaceRepository._to_face_public(
                face, uri, is_verified, person_name, candidate_person_id, candidate_person_name
            ).model_dump(),
            # 0-1 "match strength", not a raw signed cosine value: floor negative
            # similarity to 0, cap float32 rounding overshoot (1.0000001192...) to 1.
            similarity_score=max(0.0, min(1.0, similarity_score)),
        )

    async def representative_faces(self, *, verified_only: bool = False) -> list[tuple[str, str]]:
        """`(face_id, person_id)` for every representative face -- the anchors for batch matching."""
        stmt = (
            select(FaceTable.id, FaceTable.person_id)
            .join(PersonTable, PersonTable.id == FaceTable.person_id)
            .where(FaceTable.is_representative.is_(True), FaceTable.embedding.is_not(None))
        )
        if verified_only:
            stmt = stmt.where(PersonTable.is_verified.is_(True))
        rows = (await self.session.execute(stmt)).all()
        return [(r[0], r[1]) for r in rows]

    async def get_potential_person_matches(
        self,
        face_id: str,
        min_similarity: float = DEFAULT_FACE_MATCH_SIMILARITY,
        limit: int = 10_000,
        dataset_id: str | None = None,
    ) -> list[tuple[str, float]]:
        """KNN-search for still-unassigned faces similar to `face_id`, above `min_similarity`.

        The one definition of "a potential match" for a face -- proposing
        candidates for analyst review (via `FaceMatch`) after a person gains a
        new reference face, and any future ingestion-time matcher, should both
        call this rather than each constructing their own KNN query.

        Returns `(face_id, similarity_score)` pairs, similarity descending.
        Deliberately a bare index scan over `face` alone -- no uri/status
        joins, no result models -- since callers only need the ids and scores
        to write `FaceMatch` rows, and this runs inline in create-person. The
        `limit` defaults high enough (10k) to effectively return every real
        match at the expected scale, so an analyst never sees an unexplained
        "why didn't this face match?".
        """
        embedding = await self.get_embedding_by_face_id(face_id)
        if embedding is None:
            return []

        distance_expr = FaceTable.embedding.max_inner_product(embedding)
        where = [
            FaceTable.person_id.is_(None),
            FaceTable.date_rejected.is_(None),
            FaceTable.id != face_id,
            distance_expr <= -min_similarity,
        ]
        if dataset_id is not None:
            # `image` is content-keyed and dataset-agnostic; the dataset link is on `file`.
            where.append(
                exists(
                    select(literal(1)).where(
                        FileTable.sha256 == FaceTable.image_id,
                        FileTable.dataset_id == dataset_id,
                    )
                )
            )
        stmt = select(FaceTable.id, -distance_expr).where(*where).order_by(asc(distance_expr)).limit(limit)
        rows = (await self.session.execute(stmt)).all()
        return [(face_id_, max(0.0, min(1.0, score))) for face_id_, score in rows]

    # --- Face clustering (unsupervised identity discovery) -------------------
    #
    # A dataset-wide sweep, not a per-face op: pull a kNN similarity graph over
    # still-unassigned faces off the HNSW index, union-find it into clusters in
    # the workflow, and mint one (unnamed) `person` per cluster that clears the
    # size floor. All reads here filter `person_id IS NULL`, so a re-run only
    # ever considers newly detected faces.

    async def knn_face_edges(
        self,
        *,
        dataset_id: str | None = None,
        k: int = 20,
        min_similarity: float = DEFAULT_FACE_MATCH_SIMILARITY,
        max_faces: int = 200_000,
    ) -> list[tuple[str, str, float]]:
        """Similarity edges among still-unassigned faces, for clustering.

        For up to `max_faces` unassigned faces (oldest first), the HNSW index
        yields each one's `k` nearest unassigned neighbours; a pair is emitted
        when cosine similarity (`-(a <#> b)`, embeddings are L2-normalised) is
        at least `min_similarity`. Scoped to one dataset via `image.dataset_id`
        when given. Returns `(face_a, face_b, similarity)` rows (directed hits;
        the caller de-dupes via union-find).
        """
        anchor_face = aliased(FaceTable)
        neighbour = aliased(FaceTable)

        def _in_dataset(face_alias):
            # `image` is keyed by content (sha256) and dataset-agnostic; the
            # dataset link lives on `file` (file.sha256 == image.id == face.image_id).
            return exists(
                select(literal(1)).where(
                    FileTable.sha256 == face_alias.image_id,
                    FileTable.dataset_id == dataset_id,
                )
            )

        anchor_q = select(anchor_face.id.label("id"), anchor_face.embedding.label("embedding")).where(
            anchor_face.person_id.is_(None), anchor_face.date_rejected.is_(None), anchor_face.embedding.is_not(None)
        )
        if dataset_id:
            anchor_q = anchor_q.where(_in_dataset(anchor_face))
        anchor_q = anchor_q.order_by(anchor_face.date_created).limit(max_faces).subquery("anchors")

        distance = neighbour.embedding.max_inner_product(anchor_q.c.embedding)
        neighbour_q = select(neighbour.id.label("id"), (-distance).label("sim")).where(
            neighbour.person_id.is_(None),
            neighbour.date_rejected.is_(None),
            neighbour.embedding.is_not(None),
            neighbour.id != anchor_q.c.id,
        )
        if dataset_id:
            neighbour_q = neighbour_q.where(_in_dataset(neighbour))
        neighbour_q = neighbour_q.order_by(asc(distance)).limit(k).lateral("nn")

        stmt = (
            select(anchor_q.c.id, neighbour_q.c.id, neighbour_q.c.sim)
            .select_from(anchor_q)
            .join(neighbour_q, literal(True))
            .where(neighbour_q.c.sim >= min_similarity)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(a, b, max(0.0, min(1.0, float(sim)))) for a, b, sim in rows]

    async def faces_cluster_meta(self, face_ids: list[str]) -> list[tuple[str, str, float | None, float | None]]:
        """`(id, image_id, quality_score, detection_confidence)` for each face id."""
        if not face_ids:
            return []
        rows = (
            await self.session.execute(
                select(
                    FaceTable.id,
                    FaceTable.image_id,
                    FaceTable.quality_score,
                    FaceTable.detection_confidence,
                ).where(FaceTable.id.in_(face_ids))
            )
        ).all()
        return [(r[0], r[1], r[2], r[3]) for r in rows]

    async def nearest_assigned_person(
        self, face_ids: list[str], *, min_similarity: float = DEFAULT_FACE_MATCH_SIMILARITY
    ) -> tuple[str, str, bool, float] | None:
        """Closest already-assigned face to any face in the set -> its person.

        Returns `(person_id, person_source, person_is_verified, similarity)`
        for the single best hit at or above `min_similarity`, else None. Uses
        the HNSW index per input face. Lets a fresh cluster merge into an
        existing identity instead of minting a duplicate person.
        """
        if not face_ids:
            return None

        anchors = (
            select(FaceTable.embedding.label("embedding"))
            .where(FaceTable.id.in_(face_ids), FaceTable.embedding.is_not(None))
            .subquery("a")
        )
        assigned = aliased(FaceTable)
        distance = assigned.embedding.max_inner_product(anchors.c.embedding)
        nearest = (
            select(
                assigned.person_id.label("person_id"),
                PersonTable.source.label("source"),
                PersonTable.is_verified.label("is_verified"),
                (-distance).label("sim"),
            )
            .select_from(assigned)
            .join(PersonTable, PersonTable.id == assigned.person_id)
            .where(assigned.person_id.is_not(None), assigned.embedding.is_not(None))
            .order_by(asc(distance))
            .limit(1)
            .lateral("nn")
        )
        stmt = (
            select(nearest.c.person_id, nearest.c.source, nearest.c.is_verified, nearest.c.sim)
            .select_from(anchors)
            .join(nearest, literal(True))
            .where(nearest.c.sim >= min_similarity)
            .order_by(desc(nearest.c.sim))
            .limit(1)
        )
        row = (await self.session.execute(stmt)).first()
        if row is None:
            return None
        return (row[0], str(row[1]), bool(row[2]), max(0.0, min(1.0, float(row[3]))))

    async def assign_faces_to_person(
        self,
        face_ids: list[str],
        person_id: str,
        *,
        method: FaceAssignmentMethod = FaceAssignmentMethod.AUTOMATIC,
        confidence: float | None = None,
        chunk: int = 2000,
    ) -> int:
        """Bulk-link a set of faces to one person. Returns rows updated."""
        total = 0
        for start in range(0, len(face_ids), chunk):
            part = face_ids[start : start + chunk]
            result = await self.session.execute(
                update(FaceTable)
                .where(FaceTable.id.in_(part))
                .values(person_id=person_id, assignment_method=method, assignment_confidence=confidence)
            )
            total += result.rowcount or 0
        await self.session.commit()
        return total

    async def set_primary_representative(self, face_id: str) -> None:
        """Mark one already-assigned face representative + primary for its person.

        No cap / uniqueness handling -- only called once per freshly created
        clustering person, which has no other representative or primary face.
        """
        await self.session.execute(
            update(FaceTable).where(FaceTable.id == face_id).values(is_representative=True, is_primary=True)
        )
        await self.session.commit()
