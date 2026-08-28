import numpy as np
from sqlalchemy import asc, delete, desc, exists, func, literal, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.image import ImageTable
from cipher.schemas.common import SortOrder, UriResponse
from cipher.schemas.image import (
    BaseImageSearchParameters,
    Image,
    ImageCreate,
    ImagePublic,
    ImageSimilarityResult,
    ImageSimilaritySearchRequest,
    ImageSortField,
    ImageUpdate,
    PaginatedImageSimilarityResponse,
    PaginatedImagesResponse,
)


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
        "gps_altitude": excluded.gps_altitude,
        "tags": excluded.tags,
    }


def _tags_overlap_expr(tags: list[str]):
    """Build a "some element of ImageTable.tags is in `tags`" filter.

    ImageTable.tags is JSONB (not a native Postgres array), so the array
    comparator's `.overlap()` isn't available -- unnest it with
    jsonb_array_elements_text and check membership instead.
    """
    tag_elements = func.jsonb_array_elements_text(ImageTable.tags).table_valued("value")
    return exists(select(literal(1)).select_from(tag_elements).where(tag_elements.c.value.in_(tags)))


class PostgresImageRepository:
    """Postgres datastore implementation using SQLAlchemy.

    Image content is keyed by sha256 (`ImageTable.id`) and stored once no matter how many
    files share it -- every join below matches on `FileTable.sha256 == ImageTable.id`
    rather than a stored foreign key.
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

    async def get_filetypes(self) -> list[str]:
        """Get the distinct set of file types actually present among images."""
        result = await self.session.execute(
            select(FileTable.filetype)
            .join(ImageTable, ImageTable.id == FileTable.sha256)
            .distinct()
            .order_by(FileTable.filetype)
        )
        return list(result.scalars().all())

    async def delete_image(self, image_id: str) -> bool:
        """Delete image content by ID (sha256) -- removes it for every file that shares it."""
        result = await self.session.execute(
            delete(ImageTable).where(ImageTable.id == image_id)
        )
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

    async def update_image(self, image_id: str, data: ImageUpdate) -> Image | None:
        """Partially update image content (e.g. tags) -- applies to every file that shares it."""
        result = await self.session.execute(
            select(ImageTable).where(ImageTable.id == image_id)
        )
        image_table = result.scalar_one_or_none()
        if image_table is None:
            return None

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(image_table, field, value)

        await self.session.commit()
        await self.session.refresh(image_table)
        return await self.get_image_by_id(image_id)

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
            select(ImageTable)
            .join(FileTable, FileTable.sha256 == ImageTable.id)
            .where(FileTable.id == file_id)
        )
        image_table = result.scalar_one_or_none()
        if image_table is None:
            return None
        return Image.model_validate({**image_table.__dict__, "file_id": file_id})

    async def upsert_image(self, image: ImageCreate, file_id: str) -> Image:
        """Upsert image content -- insert or update if this sha256 already exists.

        `file_id` is only used to shape the response, not stored.
        """
        stmt = pg_insert(ImageTable).values(**image.model_dump())
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["id"], set_=_upsert_set(stmt.excluded)
        ).returning(ImageTable)

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

    async def get_embedding_by_image_id(
        self, image_id: str
    ) -> list[float] | None:
        """Retrieve embedding vector for a given image ID."""
        result = await self.session.execute(
            select(ImageTable.embedding).where(ImageTable.id == image_id)
        )
        embedding = result.scalar_one_or_none()

        if embedding is None:
            return None

        if isinstance(embedding, np.ndarray):
            return embedding.tolist()
        return embedding

    async def search_images(
        self, request: BaseImageSearchParameters
    ) -> PaginatedImagesResponse:
        """Retrieve images with general filtering and sorting, one row per file occurrence."""
        base_query = select(ImageTable, FileTable.id).join(
            FileTable, FileTable.sha256 == ImageTable.id
        )

        if request.datasets:
            base_query = base_query.where(FileTable.dataset_id.in_(request.datasets))

        if request.filetypes:
            base_query = base_query.where(FileTable.filetype.in_(request.filetypes))

        if request.date_from:
            base_query = base_query.where(ImageTable.date_taken >= request.date_from)

        if request.date_to:
            base_query = base_query.where(ImageTable.date_taken <= request.date_to)

        if request.tags:
            base_query = base_query.where(_tags_overlap_expr(request.tags))

        count_query = select(func.count()).select_from(base_query.subquery())
        count_result = await self.session.execute(count_query)
        total_count = count_result.scalar_one()

        sort_column = ImageTable.date_taken
        if request.sort_order == SortOrder.DESC:
            base_query = base_query.order_by(sort_column.desc())
        else:
            base_query = base_query.order_by(sort_column.asc())

        offset = (request.page - 1) * request.limit
        paginated_query = base_query.offset(offset).limit(request.limit)

        result = await self.session.execute(paginated_query)
        images = [
            ImagePublic.model_validate({**img.__dict__, "file_id": file_id})
            for img, file_id in result.all()
        ]

        total_pages = (total_count + request.limit - 1) // request.limit

        return PaginatedImagesResponse(
            total=total_count,
            page=request.page,
            limit=request.limit,
            total_pages=total_pages,
            data=images,
        )

    async def search_similar_images(
        self, request: ImageSimilaritySearchRequest
    ) -> PaginatedImageSimilarityResponse:
        """Retrieve images by knn similarity search using inner product, one row per file occurrence.

        `max_inner_product` (pgvector's `<#>`) is a *distance*: it returns the
        negative inner product, so smaller means more similar. Similarity
        sort therefore always orders ascending on it regardless of
        `sort_order` -- that toggle only applies to the date-sort branch --
        mirroring `PostgresFaceRepository.search_similar_faces`.
        """
        distance_expr = ImageTable.embedding.max_inner_product(request.embedding)

        filters = []
        if request.datasets:
            filters.append(FileTable.dataset_id.in_(request.datasets))
        if request.filetypes:
            filters.append(FileTable.filetype.in_(request.filetypes))
        if request.date_from:
            filters.append(ImageTable.date_taken >= request.date_from)
        if request.date_to:
            filters.append(ImageTable.date_taken <= request.date_to)
        if request.tags:
            filters.append(_tags_overlap_expr(request.tags))
        if request.min_similarity is not None:
            filters.append(distance_expr <= -request.min_similarity)

        count_query = (
            select(func.count(ImageTable.id))
            .join(FileTable, FileTable.sha256 == ImageTable.id)
            .where(*filters)
        )
        count_result = await self.session.execute(count_query)
        total_count = count_result.scalar_one()

        base_query = (
            select(ImageTable, FileTable.id, (-distance_expr).label("similarity_score"))
            .join(FileTable, FileTable.sha256 == ImageTable.id)
            .where(*filters)
        )

        if request.sort_by == ImageSortField.SIMILARITY:
            base_query = base_query.order_by(asc(distance_expr))
        else:
            sort_col = ImageTable.date_taken
            if request.sort_order == SortOrder.DESC:
                base_query = base_query.order_by(desc(sort_col))
            else:
                base_query = base_query.order_by(asc(sort_col))

        offset = (request.page - 1) * request.limit
        paginated_query = base_query.offset(offset).limit(request.limit)

        result = await self.session.execute(paginated_query)
        rows = list(result.all())

        images = [
            ImageSimilarityResult.model_validate({
                **ImagePublic.model_validate({**image.__dict__, "file_id": file_id}).model_dump(),
                "similarity_score": max(0.0, min(1.0, similarity_score)),
            })
            for image, file_id, similarity_score in rows
        ]

        total_pages = (total_count + request.limit - 1) // request.limit

        return PaginatedImageSimilarityResponse(
            total=total_count,
            page=request.page,
            limit=request.limit,
            total_pages=total_pages,
            data=images,
        )
