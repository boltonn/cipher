import numpy as np
from sqlalchemy import Float, and_, asc, delete, desc, exists, func, literal, or_, select, tablesample, text
from sqlalchemy.dialects.postgresql import array, insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from cipher.datastores.postgres.repositories.tag import PostgresTagRepository
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.image import IMAGE_EMBEDDING_DIMENSION, ImageTable
from cipher.datastores.postgres.tables.tag import TagTable
from cipher.schemas._base.common import ModelTagType, SortOrder, UriResponse
from cipher.schemas.content.image import (
    BaseImageSearchParameters,
    Image,
    ImageCreate,
    ImagePublic,
    ImageSimilarityResult,
    ImageSimilaritySearchRequest,
    ImageSortField,
    ImageTagResult,
    ImageUpdate,
    PaginatedImageSimilarityResponse,
    PaginatedImagesResponse,
)
from cipher.schemas.ingestion.file import File
from cipher.schemas.interaction.tag import TagSource, TagTargetType


def _upsert_set(excluded) -> dict:
    return {
        "embedding": excluded.embedding,
        "embedding_model": excluded.embedding_model,
        "width": excluded.width,
        "height": excluded.height,
        "camera_make": excluded.camera_make,
        "camera_model": excluded.camera_model,
        "focal_length": excluded.focal_length,
        "aperture": excluded.aperture,
        "iso": excluded.iso,
        "date_taken": excluded.date_taken,
        "gps_latitude": excluded.gps_latitude,
        "gps_longitude": excluded.gps_longitude,
        "gps_altitude": excluded.gps_altitude,
    }


def _tag_score(tag: str):
    """`tag_scores[tag]` as a float (NULL when the tag was never scored)."""
    return ImageTable.tag_scores[tag].astext.cast(Float)


def _predicted_expr(tags: list[str], min_tag_score: float):
    """Build an "image has an unlabelled prediction for any of `tags`" filter.

    The scores come from `tag`, an index range scan on `ix_tag_score`; the label checks use
    the GIN indexes on `tags` / `negative_tags`.
    """
    return or_(
        *(
            and_(
                ImageTable.id.in_(
                    select(TagTable.target_id).where(
                        TagTable.target_type == TagTargetType.CONTENT,
                        TagTable.tag == tag,
                        TagTable.score >= min_tag_score,
                    )
                ),
                ~ImageTable.tags.has_key(tag),
                ~ImageTable.negative_tags.has_key(tag),
            )
            for tag in tags
        )
    )


def _file_scoped_expr(datasets: list[str] | None, filetypes: list[str] | None):
    """Build an "image belongs to at least one file matching these file-level filters".

    `datasets`/`filetypes` are file attributes, so instead of joining `file` (which
    fans a row out per file that shares the image's sha256) the search matches on
    an EXISTS against `file` -- keeping one row per distinct image.
    """
    conditions = [FileTable.sha256 == ImageTable.id]
    if datasets:
        conditions.append(FileTable.dataset_id.in_(datasets))
    if filetypes:
        conditions.append(FileTable.filetype.in_(filetypes))
    return exists(select(literal(1)).select_from(FileTable).where(*conditions))


def _search_filters(request: BaseImageSearchParameters) -> list:
    """Filters shared by the browse and similarity searches."""
    filters = []
    if request.datasets or request.filetypes:
        filters.append(_file_scoped_expr(request.datasets, request.filetypes))
    if request.date_from:
        filters.append(ImageTable.date_taken >= request.date_from)
    if request.date_to:
        filters.append(ImageTable.date_taken <= request.date_to)
    if request.tags:
        filters.append(ImageTable.tags.has_any(array(request.tags)))
    if request.negative_tags:
        filters.append(ImageTable.negative_tags.has_any(array(request.negative_tags)))
    if request.predicted_tags:
        filters.append(_predicted_expr(request.predicted_tags, request.min_tag_score))
    return filters


class PostgresImageRepository:
    """Postgres datastore implementation using SQLAlchemy.

    Image content is keyed by sha256 (`ImageTable.id`) and stored once no matter how many
    files share it -- the link to `file` is always `FileTable.sha256 == ImageTable.id`,
    not a stored foreign key. Search/list methods return one row per distinct image; the
    set of files an image belongs to is a separate lookup (`get_files_for_image`).
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the image table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(ImageTable.metadata.create_all)
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    async def create_vector_index(self, m: int = 16, ef_construction: int = 64):
        """Manually create the HNSW index for vector similarity search."""
        sql = text(f"""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS hnsw_idx_embedding
            ON image USING hnsw (embedding vector_ip_ops)
            WITH (m = {m}, ef_construction = {ef_construction});
        """)
        async with self.session.bind.begin() as conn:
            await conn.execute(sql)
            await conn.commit()

    async def get_count(self) -> int:
        """Get total count of images."""
        result = await self.session.execute(select(func.count(ImageTable.id)))
        return result.scalar_one()

    async def get_filetypes(self, datasets: list[str] | None = None) -> list[str]:
        """Get the distinct set of file types actually present among images.

        Args:
            datasets: Only count images from these datasets; None means every dataset.
        """
        stmt = select(FileTable.filetype).join(ImageTable, ImageTable.id == FileTable.sha256)
        if datasets:
            stmt = stmt.where(FileTable.dataset_id.in_(datasets))
        result = await self.session.execute(stmt.distinct().order_by(FileTable.filetype))
        return list(result.scalars().all())

    async def delete_image(self, image_id: str) -> bool:
        """Delete image content by ID (sha256) -- removes it for every file that shares it."""
        result = await self.session.execute(delete(ImageTable).where(ImageTable.id == image_id))
        await self.session.commit()
        return bool(result.rowcount)

    async def add_image(self, image: ImageCreate, file_id: str) -> Image:
        """Add image content for `file_id`.

        Returns the existing row if this sha256 (`image.id`) is already stored --
        `file_id` is only used to shape the response, not stored.
        """
        stmt = (
            pg_insert(ImageTable)
            .values(**image.model_dump())
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(ImageTable)
        )
        result = await self.session.execute(stmt)
        image_table = result.scalar_one_or_none()
        await self.session.commit()

        if image_table is not None:
            return Image.model_validate({**image_table.__dict__, "file_id": file_id})

        existing = await self.get_image_by_id(image.id)
        assert existing is not None, f"Image insert conflicted but no row found for id={image.id}"
        return existing

    async def get_image_by_id(self, image_id: str) -> Image | None:
        """Retrieve image content by ID (sha256), with a representative file_id attached."""
        result = await self.session.execute(
            select(ImageTable, FileTable.id)
            .join(FileTable, FileTable.sha256 == ImageTable.id)
            .where(ImageTable.id == image_id)
            .limit(1)
        )
        row = result.one_or_none()
        if row is None:
            return None
        image_table, file_id = row
        return Image.model_validate({**image_table.__dict__, "file_id": file_id})

    async def update_image(self, image_id: str, data: ImageUpdate, *, user_id: str) -> Image | None:
        """Partially update image content -- applies to every file that shares it.

        A `tags` list sets the positive labels as `user_id` (recording only what changed).
        """
        result = await self.session.execute(select(ImageTable).where(ImageTable.id == image_id))
        image_table = result.scalar_one_or_none()
        if image_table is None:
            return None

        for field, value in data.model_dump(exclude_unset=True, exclude={"tags"}).items():
            setattr(image_table, field, value)
        await self.session.commit()
        if data.tags is not None:
            await PostgresTagRepository(self.session).set_tags(
                target_type=TagTargetType.CONTENT,
                target_id=image_id,
                tags=data.tags,
                source=TagSource.user(user_id),
            )
        return await self.get_image_by_id(image_id)

    async def tag_images(
        self, *, image_ids: list[str], tag: str, tag_type: ModelTagType | None, user_id: str
    ) -> ImageTagResult:
        """Label images with `tag` as `user_id`: positive or negative (the latest label wins), None clears it."""
        existing = await self.session.execute(select(ImageTable.id).where(ImageTable.id.in_(image_ids)))
        found = list(existing.scalars().all())
        await PostgresTagRepository(self.session).label(
            target_type=TagTargetType.CONTENT,
            target_ids=found,
            tag=tag,
            label=tag_type,
            source=TagSource.user(user_id),
        )
        return ImageTagResult(updated=len(found))

    async def annotate_images(
        self, *, tag: str, positive: list[str], negative: list[str], cleared: list[str], user_id: str
    ) -> ImageTagResult:
        """Save one tag's labels for a batch of images as `user_id` in a single transaction."""
        tag_repo = PostgresTagRepository(self.session)
        for label, image_ids in ((ModelTagType.POSITIVE, positive), (ModelTagType.NEGATIVE, negative), (None, cleared)):
            await tag_repo.label(
                target_type=TagTargetType.CONTENT,
                target_ids=image_ids,
                tag=tag,
                label=label,
                source=TagSource.user(user_id),
                commit=False,
            )
        await self.session.commit()
        return ImageTagResult(updated=len({*positive, *negative, *cleared}))

    async def set_tag_scores(self, *, tag: str, scores: dict[str, float], model: str) -> None:
        """Record `model`'s confidence that `tag` applies, keyed by image id (sha256)."""
        await PostgresTagRepository(self.session).score(
            target_type=TagTargetType.CONTENT, tag=tag, scores=scores, model=model
        )

    async def get_image_uri(self, image_id: str) -> UriResponse | None:
        """Retrieve a URI to download this image's content from (any file with it will do)."""
        result = await self.session.execute(
            select(FileTable.uri, FileTable.mime_type)
            .join(ImageTable, ImageTable.id == FileTable.sha256)
            .where(ImageTable.id == image_id)
            .limit(1)
        )
        row = result.one_or_none()

        if row:
            uri, mime_type = row
            return UriResponse(uri=uri, mime_type=mime_type)
        return None

    async def get_image_by_file_id(self, file_id: str) -> Image | None:
        """Retrieve image content for a given file (resolved via the file's sha256)."""
        result = await self.session.execute(
            select(ImageTable).join(FileTable, FileTable.sha256 == ImageTable.id).where(FileTable.id == file_id)
        )
        image_table = result.scalar_one_or_none()
        if image_table is None:
            return None
        return Image.model_validate({**image_table.__dict__, "file_id": file_id})

    async def get_files_for_image(self, image_id: str) -> list[File]:
        """List every file whose content is this image (matched on sha256)."""
        result = await self.session.execute(
            select(FileTable).where(FileTable.sha256 == image_id).order_by(FileTable.id)
        )
        return [File.model_validate(f) for f in result.scalars().all()]

    async def upsert_image(self, image: ImageCreate, file_id: str) -> Image:
        """Upsert image content -- insert or update if this sha256 already exists.

        `file_id` is only used to shape the response, not stored.
        """
        stmt = pg_insert(ImageTable).values(**image.model_dump())
        upsert_stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=_upsert_set(stmt.excluded)).returning(
            ImageTable
        )

        result = await self.session.execute(upsert_stmt)
        await self.session.commit()

        image_table = result.scalar_one()
        return Image.model_validate({**image_table.__dict__, "file_id": file_id})

    async def upsert_image_batch(self, images: list[ImageCreate]) -> None:
        """Upsert a batch of image content rows."""
        if not images:
            return

        rows = [img.model_dump() for img in images]

        stmt = pg_insert(ImageTable).values(rows)
        upsert_stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=_upsert_set(stmt.excluded))

        await self.session.execute(upsert_stmt)
        await self.session.commit()

        del rows

    async def get_embedding_by_image_id(self, image_id: str) -> list[float] | None:
        """Retrieve embedding vector for a given image ID."""
        result = await self.session.execute(select(ImageTable.embedding).where(ImageTable.id == image_id))
        embedding = result.scalar_one_or_none()

        if embedding is None:
            return None

        if isinstance(embedding, np.ndarray):
            return embedding.tolist()
        return embedding

    async def get_embeddings(self, image_ids: list[str]) -> dict[str, list[float]]:
        """`{image_id: embedding}` for the given ids that have been embedded."""
        if not image_ids:
            return {}
        result = await self.session.execute(
            select(ImageTable.id, ImageTable.embedding).where(
                ImageTable.id.in_(image_ids), ImageTable.embedding.is_not(None)
            )
        )
        return {image_id: np.asarray(embedding).tolist() for image_id, embedding in result.all()}

    async def labelled_embeddings(
        self, *, tags: list[str] | None, embedding_model: str
    ) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """Per tag: (positive, hard-negative) embeddings of images labelled with it, from one embedding model.

        `tags=None` means every tag with at least one label. GIN-indexed on `tags` / `negative_tags`.
        """
        label_filter = (
            or_(ImageTable.tags.has_any(array(tags)), ImageTable.negative_tags.has_any(array(tags)))
            if tags
            else or_(
                func.jsonb_array_length(ImageTable.tags) > 0, func.jsonb_array_length(ImageTable.negative_tags) > 0
            )
        )
        rows = await self.session.execute(
            select(ImageTable.tags, ImageTable.negative_tags, ImageTable.embedding).where(
                label_filter, ImageTable.embedding.is_not(None), ImageTable.embedding_model == embedding_model
            )
        )
        positives: dict[str, list] = {}
        negatives: dict[str, list] = {}
        for row_tags, row_negative_tags, embedding in rows.all():
            for tag in row_tags:
                positives.setdefault(tag, []).append(embedding)
            for tag in row_negative_tags:
                negatives.setdefault(tag, []).append(embedding)
        wanted = tags or sorted(positives.keys() | negatives.keys())
        dim = IMAGE_EMBEDDING_DIMENSION
        return {
            tag: (
                np.asarray(positives.get(tag, []), dtype=np.float32).reshape(-1, dim),
                np.asarray(negatives.get(tag, []), dtype=np.float32).reshape(-1, dim),
            )
            for tag in wanted
        }

    async def sample_unlabeled_embeddings(self, *, tags: list[str], embedding_model: str, limit: int) -> np.ndarray:
        """Up to `limit` random embeddings of images labelled with none of `tags` (weak negatives).

        Uses `TABLESAMPLE` sized from the table's row count, so it reads a fraction of the table, not all of it.
        """
        if limit <= 0:
            return np.empty((0, IMAGE_EMBEDDING_DIMENSION), dtype=np.float32)
        total = await self.session.scalar(select(func.count()).select_from(ImageTable)) or 1
        percent = min(100.0, 300.0 * limit / total)
        sampled = aliased(ImageTable, tablesample(ImageTable, func.bernoulli(percent)))
        rows = await self.session.execute(
            select(sampled.embedding)
            .where(
                sampled.embedding.is_not(None),
                sampled.embedding_model == embedding_model,
                ~sampled.tags.has_any(array(tags)),
                ~sampled.negative_tags.has_any(array(tags)),
            )
            .limit(limit)
        )
        return np.asarray([e for (e,) in rows.all()], dtype=np.float32).reshape(-1, IMAGE_EMBEDDING_DIMENSION)

    async def embedding_batches(self, *, embedding_model: str, dataset_id: str | None = None, batch_size: int = 4096):
        """Yield `(image_ids, [N, D] embeddings)` batches in id order (keyset paging, no OFFSET)."""
        after = ""
        while True:
            stmt = (
                select(ImageTable.id, ImageTable.embedding)
                .where(
                    ImageTable.id > after,
                    ImageTable.embedding.is_not(None),
                    ImageTable.embedding_model == embedding_model,
                )
                .order_by(ImageTable.id)
                .limit(batch_size)
            )
            if dataset_id:
                stmt = stmt.where(_file_scoped_expr([dataset_id], None))
            rows = (await self.session.execute(stmt)).all()
            if not rows:
                return
            yield [r[0] for r in rows], np.asarray([r[1] for r in rows], dtype=np.float32)
            after = rows[-1][0]

    async def search_images(self, request: BaseImageSearchParameters) -> PaginatedImagesResponse:
        """Retrieve images with general filtering and sorting, one row per distinct image.

        Results are keyed by sha256 (`ImageTable.id`) only -- content is
        deduplicated across files. `datasets`/`filetypes` are file attributes, so
        they filter via an EXISTS against `file` (see `_file_scoped_expr`) rather
        than a join that would fan a row out per file. The files an image belongs
        to are fetched separately via `get_files_for_image`.
        """
        filters = _search_filters(request)

        count_query = select(func.count()).select_from(ImageTable).where(*filters)
        total_count = (await self.session.execute(count_query)).scalar_one()

        # `tag_score` ranks by the first predicted tag's score, so predictions are reviewed in confidence order.
        is_score_sort = request.sort_by == ImageSortField.TAG_SCORE and request.predicted_tags
        sort_column = _tag_score(request.predicted_tags[0]) if is_score_sort else ImageTable.date_taken
        direction = sort_column.desc() if request.sort_order == SortOrder.DESC else sort_column.asc()
        # ImageTable.id is unique -- append it so offset pagination is
        # deterministic even when the sort key is null or shared.
        paginated_query = (
            select(ImageTable)
            .where(*filters)
            .order_by(direction.nulls_last(), ImageTable.id)
            .offset((request.page - 1) * request.limit)
            .limit(request.limit)
        )

        result = await self.session.execute(paginated_query)
        images = [ImagePublic.model_validate(img.__dict__) for img in result.scalars().all()]

        total_pages = (total_count + request.limit - 1) // request.limit

        return PaginatedImagesResponse(
            total=total_count,
            page=request.page,
            limit=request.limit,
            total_pages=total_pages,
            data=images,
        )

    async def search_similar_images(self, request: ImageSimilaritySearchRequest) -> PaginatedImageSimilarityResponse:
        """Retrieve images by knn similarity search using inner product, one row per distinct image.

        `max_inner_product` (pgvector's `<#>`) is a *distance*: it returns the
        negative inner product, so smaller means more similar. Similarity
        sort therefore always orders ascending on it regardless of
        `sort_order` -- that toggle only applies to the date-sort branch --
        mirroring `PostgresFaceRepository.search_similar_faces`.

        Results are keyed by sha256 (`ImageTable.id`) only -- the embedding lives
        on the image, so file occurrences are irrelevant to ranking. File-level
        filters go through an EXISTS against `file` (no join, no fan-out), which
        also keeps pgvector's index usable for the similarity `ORDER BY`.
        """
        distance_expr = ImageTable.embedding.max_inner_product(request.embedding)

        filters = _search_filters(request)
        if request.min_similarity is not None:
            filters.append(distance_expr <= -request.min_similarity)

        count_query = select(func.count()).select_from(ImageTable).where(*filters)
        total_count = (await self.session.execute(count_query)).scalar_one()

        base_query = select(ImageTable, (-distance_expr).label("similarity_score")).where(*filters)

        if request.sort_by == ImageSortField.SIMILARITY:
            primary_sort = asc(distance_expr)
        else:
            sort_col = ImageTable.date_taken
            primary_sort = desc(sort_col) if request.sort_order == SortOrder.DESC else asc(sort_col)
        # ImageTable.id is unique -- append it so offset pagination is
        # deterministic when the primary sort key has ties.
        paginated_query = (
            base_query.order_by(primary_sort, ImageTable.id)
            .offset((request.page - 1) * request.limit)
            .limit(request.limit)
        )

        result = await self.session.execute(paginated_query)
        rows = list(result.all())

        images = [
            ImageSimilarityResult.model_validate(
                {
                    **ImagePublic.model_validate(image.__dict__).model_dump(),
                    "similarity_score": max(0.0, min(1.0, similarity_score)),
                }
            )
            for image, similarity_score in rows
        ]

        total_pages = (total_count + request.limit - 1) // request.limit

        return PaginatedImageSimilarityResponse(
            total=total_count,
            page=request.page,
            limit=request.limit,
            total_pages=total_pages,
            data=images,
        )
