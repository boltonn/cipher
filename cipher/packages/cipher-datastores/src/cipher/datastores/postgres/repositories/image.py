import numpy as np
from sqlalchemy import asc, delete, desc, func, select, text
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
    ImageSimilaritySearchRequest,
    ImageSortField,
    PaginatedImagesResponse,
)


class PostgresImageRepository:
    """Postgres datastore implementation using SQLAlchemy."""

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

    async def delete_image(self, image_id: str) -> bool:
        """Delete an image by ID."""
        result = await self.session.execute(
            delete(ImageTable).where(ImageTable.id == image_id)
        )
        await self.session.commit()
        return bool(result.rowcount)

    async def add_image(self, image: ImageCreate) -> Image:
        """Add a single image, returning existing if file_id conflict exists."""
        result = await self.session.execute(
            select(ImageTable).where(ImageTable.file_id == image.file_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return Image.model_validate(existing)

        image_table = ImageTable(**image.model_dump())
        self.session.add(image_table)
        await self.session.commit()
        await self.session.refresh(image_table)

        return Image.model_validate(image_table)

    async def get_image_by_id(self, image_id: str) -> Image | None:
        """Retrieve image by ID."""
        result = await self.session.execute(
            select(ImageTable).where(ImageTable.id == image_id)
        )
        image_table = result.scalar_one_or_none()
        return Image.model_validate(image_table) if image_table else None

    async def get_image_uri(self, image_id: str) -> UriResponse | None:
        """Retrieve image URI by ID."""
        result = await self.session.execute(
            select(FileTable.uri, FileTable.mime_type)
            .join(ImageTable, ImageTable.file_id == FileTable.id)
            .where(ImageTable.id == image_id)
            .limit(1)
        )
        row = result.one_or_none()

        if row:
            uri, mime_type = row
            return UriResponse(uri=uri, mime_type=mime_type)
        return None

    async def get_image_by_file_id(self, file_id: str) -> Image | None:
        """Retrieve image by file ID."""
        result = await self.session.execute(
            select(ImageTable).where(ImageTable.file_id == file_id)
        )
        image_table = result.scalar_one_or_none()
        return Image.model_validate(image_table) if image_table else None

    async def upsert_image(self, image: ImageCreate) -> Image:
        """Upsert image - insert or update if file_id exists."""
        data = image.model_dump()

        stmt = pg_insert(ImageTable).values(**data)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["file_id"],
            set_={
                "embedding": stmt.excluded.embedding,
                "embedding_model": stmt.excluded.embedding_model,
                "width": stmt.excluded.width,
                "height": stmt.excluded.height,
                "camera_make": stmt.excluded.camera_make,
                "camera_model": stmt.excluded.camera_model,
                "focal_length": stmt.excluded.focal_length,
                "aperture": stmt.excluded.aperture,
                "iso": stmt.excluded.iso,
                "date_taken": stmt.excluded.date_taken,
                "gps_altitude": stmt.excluded.gps_altitude,
                "tags": stmt.excluded.tags,
            },
        ).returning(ImageTable)

        result = await self.session.execute(upsert_stmt)
        await self.session.commit()

        image_table = result.scalar_one()
        return Image.model_validate(image_table)

    async def upsert_image_batch(self, images: list[ImageCreate]) -> None:
        """Upsert a batch of images."""
        if not images:
            return

        rows = [img.model_dump() for img in images]

        stmt = pg_insert(ImageTable).values(rows)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["file_id"],
            set_={
                "embedding": stmt.excluded.embedding,
                "embedding_model": stmt.excluded.embedding_model,
                "width": stmt.excluded.width,
                "height": stmt.excluded.height,
                "camera_make": stmt.excluded.camera_make,
                "camera_model": stmt.excluded.camera_model,
                "focal_length": stmt.excluded.focal_length,
                "aperture": stmt.excluded.aperture,
                "iso": stmt.excluded.iso,
                "date_taken": stmt.excluded.date_taken,
                "gps_altitude": stmt.excluded.gps_altitude,
                "tags": stmt.excluded.tags,
            },
        )

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
        """Retrieve images with general filtering and sorting."""
        base_query = select(ImageTable).join(
            FileTable, ImageTable.file_id == FileTable.id
        )

        if request.filetypes:
            base_query = base_query.where(FileTable.filetype.in_(request.filetypes))

        if request.date_from:
            base_query = base_query.where(ImageTable.date_taken >= request.date_from)

        if request.date_to:
            base_query = base_query.where(ImageTable.date_taken <= request.date_to)

        if request.tags:
            base_query = base_query.where(ImageTable.tags.overlap(request.tags))

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
        images = [ImagePublic.model_validate(img) for img in result.scalars().all()]

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
    ) -> PaginatedImagesResponse:
        """Retrieve images by knn similarity search using inner product."""
        distance_expr = ImageTable.embedding.max_inner_product(request.embedding)

        filters = []
        if request.filetypes:
            filters.append(FileTable.filetype.in_(request.filetypes))
        if request.date_from:
            filters.append(ImageTable.date_taken >= request.date_from)
        if request.date_to:
            filters.append(ImageTable.date_taken <= request.date_to)
        if request.tags:
            filters.append(ImageTable.tags.overlap(request.tags))
        if request.min_similarity is not None:
            filters.append(distance_expr <= -request.min_similarity)

        count_query = (
            select(func.count(ImageTable.id))
            .join(FileTable, ImageTable.file_id == FileTable.id)
            .where(*filters)
        )
        count_result = await self.session.execute(count_query)
        total_count = count_result.scalar_one()

        base_query = (
            select(ImageTable, distance_expr.label("neg_ip"))
            .join(FileTable, ImageTable.file_id == FileTable.id)
            .where(*filters)
        )

        if request.sort_by == ImageSortField.SIMILARITY:
            if request.sort_order == SortOrder.DESC:
                base_query = base_query.order_by(desc(distance_expr))
            else:
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

        images = [ImagePublic.model_validate(image) for image, neg_ip in rows]

        total_pages = (total_count + request.limit - 1) // request.limit

        return PaginatedImagesResponse(
            total=total_count,
            page=request.page,
            limit=request.limit,
            total_pages=total_pages,
            data=images,
        )
