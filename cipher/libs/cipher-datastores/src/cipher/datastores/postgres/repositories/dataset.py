from loguru import logger
from sqlalchemy import asc, delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.dataset import DatasetTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.schemas.ingestion.dataset import (
    Dataset,
    DatasetCreate,
    DatasetSortField,
    DatasetsRequest,
    DatasetStatsRequest,
    DatasetStatsResponse,
    DatasetSummary,
    DatasetUpdate,
    FiletypeBreakdownItem,
    LoadHistogramBucket,
    PaginatedDatasetsResponse,
    SortOrder,
)


class PostgresDatasetRepository:
    """Postgres datastore implementation using SQLAlchemy."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the dataset table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(DatasetTable.metadata.create_all)

    async def delete_table(self):
        """Drop the dataset table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(DatasetTable.metadata.drop_all)

    async def get_count(self) -> int:
        """Get total count of datasets."""
        result = await self.session.execute(select(func.count(DatasetTable.id)))
        return result.scalar_one()

    async def delete_dataset(self, dataset_id: str) -> bool:
        """Delete a dataset by ID. Returns True if deleted, False if not found."""
        result = await self.session.execute(
            delete(DatasetTable).where(DatasetTable.id == dataset_id)
        )
        await self.session.commit()
        return result.rowcount > 0

    async def add_dataset(self, dataset: DatasetCreate) -> Dataset:
        """Add a new dataset if it doesn't exist, otherwise return the existing dataset."""
        # Check if dataset with this name already exists
        result = await self.session.execute(
            select(DatasetTable).where(DatasetTable.name == dataset.name)
        )
        existing = result.scalar_one_or_none()

        if existing:
            return Dataset.model_validate(existing)

        # Create new dataset
        data = dataset.model_dump()
        dataset_table = DatasetTable(**data)

        self.session.add(dataset_table)
        await self.session.commit()
        await self.session.refresh(dataset_table)

        return Dataset.model_validate(dataset_table)

    async def add_datasets(
        self, datasets: list[DatasetCreate], refresh: bool = False
    ) -> list[Dataset]:
        """Bulk add datasets to the database."""
        # Convert to table models
        dataset_tables = [DatasetTable(**ds.model_dump()) for ds in datasets]

        self.session.add_all(dataset_tables)
        await self.session.commit()

        if refresh:
            dataset_ids = [ds.id for ds in dataset_tables]
            result = await self.session.execute(
                select(DatasetTable).where(DatasetTable.id.in_(dataset_ids))
            )
            dataset_tables = list(result.scalars().all())

        return [Dataset.model_validate(ds) for ds in dataset_tables]

    async def get_dataset_by_id(self, dataset_id: str) -> Dataset | None:
        """Retrieve dataset by ID."""
        result = await self.session.execute(
            select(DatasetTable).where(DatasetTable.id == dataset_id)
        )
        dataset_table = result.scalar_one_or_none()

        return Dataset.model_validate(dataset_table) if dataset_table else None

    async def get_datasets(
        self, request: DatasetsRequest | dict | None = None
    ) -> PaginatedDatasetsResponse:
        """Query datasets with filtering, pagination, and sorting.

        Each row is enriched with file_count/total_size_bytes/filetype_count
        aggregated from `file`, via a LEFT JOIN so empty datasets still
        appear (with zero stats) rather than being dropped by an inner join.
        """
        if isinstance(request, dict):
            request = DatasetsRequest(**request)
        elif request is None:
            request = DatasetsRequest()

        file_stats = (
            select(
                FileTable.dataset_id.label("dataset_id"),
                func.count(FileTable.id).label("file_count"),
                func.coalesce(func.sum(FileTable.size), 0).label("total_size_bytes"),
                func.count(func.distinct(FileTable.filetype)).label("filetype_count"),
            )
            .group_by(FileTable.dataset_id)
            .subquery()
        )
        file_count_expr = func.coalesce(file_stats.c.file_count, 0)
        total_size_expr = func.coalesce(file_stats.c.total_size_bytes, 0)
        filetype_count_expr = func.coalesce(file_stats.c.filetype_count, 0)

        where_clause = []
        if request.query:
            where_clause.append(
                or_(
                    DatasetTable.name.ilike(f"%{request.query}%"),
                    DatasetTable.description.ilike(f"%{request.query}%"),
                )
            )
        if request.date_created_from:
            where_clause.append(DatasetTable.date_created >= request.date_created_from)
        if request.date_created_to:
            where_clause.append(DatasetTable.date_created <= request.date_created_to)
        if request.date_last_updated_from:
            where_clause.append(DatasetTable.date_last_updated >= request.date_last_updated_from)
        if request.date_last_updated_to:
            where_clause.append(DatasetTable.date_last_updated <= request.date_last_updated_to)

        count_stmt = select(func.count(DatasetTable.id))
        if where_clause:
            count_stmt = count_stmt.where(*where_clause)
        count_result = await self.session.execute(count_stmt)
        total_count = count_result.scalar_one()

        data_stmt = (
            select(DatasetTable, file_count_expr, total_size_expr, filetype_count_expr)
            .outerjoin(file_stats, DatasetTable.id == file_stats.c.dataset_id)
        )
        if where_clause:
            data_stmt = data_stmt.where(*where_clause)

        sort_column = {
            DatasetSortField.NAME: DatasetTable.name,
            DatasetSortField.DATE_CREATED: DatasetTable.date_created,
            DatasetSortField.DATE_LAST_UPDATED: DatasetTable.date_last_updated,
            DatasetSortField.FILE_COUNT: file_count_expr,
            DatasetSortField.TOTAL_SIZE_BYTES: total_size_expr,
            DatasetSortField.FILETYPE_COUNT: filetype_count_expr,
        }[DatasetSortField(request.sort_by)]
        data_stmt = data_stmt.order_by(
            desc(sort_column) if request.sort_order == SortOrder.DESC else asc(sort_column)
        )

        data_stmt = data_stmt.offset((request.page - 1) * request.limit).limit(
            request.limit
        )

        data_result = await self.session.execute(data_stmt)
        datasets = [
            DatasetSummary.model_validate({
                **Dataset.model_validate(dataset_table).model_dump(),
                "file_count": file_count,
                "total_size_bytes": total_size_bytes,
                "filetype_count": filetype_count,
            })
            for dataset_table, file_count, total_size_bytes, filetype_count in data_result.all()
        ]

        total_pages = (total_count + request.limit - 1) // request.limit

        return PaginatedDatasetsResponse(
            total=total_count,
            page=request.page,
            limit=request.limit,
            total_pages=total_pages,
            data=datasets,
        )

    async def get_dataset_stats(
        self, dataset_id: str, request: DatasetStatsRequest
    ) -> DatasetStatsResponse:
        """Aggregate a dataset's files by filetype, group, and load time bucket.

        All three breakdowns are scoped to the same requested date range.
        """
        where_clause = [FileTable.dataset_id == dataset_id]
        if request.date_from:
            where_clause.append(FileTable.date_loaded >= request.date_from)
        if request.date_to:
            where_clause.append(FileTable.date_loaded <= request.date_to)
        if request.filetype:
            where_clause.append(FileTable.filetype == request.filetype)
        if request.filetype_group:
            where_clause.append(FileTable.filetype_group == request.filetype_group)

        total_files, total_size_bytes = (
            await self.session.execute(
                select(
                    func.count(FileTable.id),
                    func.coalesce(func.sum(FileTable.size), 0),
                ).where(*where_clause)
            )
        ).one()

        filetype_rows = await self.session.execute(
            select(FileTable.filetype, func.count(FileTable.id))
            .where(*where_clause)
            .group_by(FileTable.filetype)
            .order_by(desc(func.count(FileTable.id)))
        )
        by_filetype = [
            FiletypeBreakdownItem(filetype=filetype, count=count)
            for filetype, count in filetype_rows.all()
        ]

        filetype_group_rows = await self.session.execute(
            select(FileTable.filetype_group, func.count(FileTable.id))
            .where(*where_clause)
            .group_by(FileTable.filetype_group)
            .order_by(desc(func.count(FileTable.id)))
        )
        by_filetype_group = [
            FiletypeBreakdownItem(filetype=filetype_group, count=count)
            for filetype_group, count in filetype_group_rows.all()
        ]

        bucket_expr = func.date_trunc(request.granularity, FileTable.date_loaded)
        histogram_rows = await self.session.execute(
            select(bucket_expr.label("bucket"), func.count(FileTable.id))
            .where(*where_clause)
            .group_by(bucket_expr)
            .order_by(bucket_expr)
        )
        loaded_over_time = [
            LoadHistogramBucket(date_bucket=bucket, count=count)
            for bucket, count in histogram_rows.all()
        ]

        return DatasetStatsResponse(
            total_files=total_files,
            total_size_bytes=total_size_bytes,
            by_filetype=by_filetype,
            by_filetype_group=by_filetype_group,
            loaded_over_time=loaded_over_time,
        )

    async def update_dataset(
        self, dataset_id: str, data: DatasetUpdate
    ) -> Dataset:
        """Update a dataset by ID."""
        update_dict = data.model_dump(exclude_unset=True, by_alias=False)
        logger.info(f"Updating dataset {dataset_id} with: {update_dict}")

        stmt = (
            update(DatasetTable)
            .where(DatasetTable.id == dataset_id)
            .values(**update_dict)
            .returning(DatasetTable)
        )

        result = await self.session.execute(stmt)
        await self.session.commit()

        dataset_table = result.scalar_one_or_none()

        if not dataset_table:
            raise ValueError(f"Dataset not found: {dataset_id}")

        return Dataset.model_validate(dataset_table)

    async def exists(self, dataset_id: str) -> bool:
        """Check if a dataset exists."""
        result = await self.session.execute(
            select(func.count(DatasetTable.id)).where(DatasetTable.id == dataset_id)
        )
        return result.scalar_one() > 0

    async def get_by_name(self, name: str) -> Dataset | None:
        """Get a dataset by name."""
        result = await self.session.execute(
            select(DatasetTable).where(DatasetTable.name == name)
        )
        dataset_table = result.scalar_one_or_none()
        return Dataset.model_validate(dataset_table) if dataset_table else None
