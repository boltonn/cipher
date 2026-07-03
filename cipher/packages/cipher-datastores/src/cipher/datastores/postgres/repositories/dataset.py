from loguru import logger
from pydantic.alias_generators import to_snake
from sqlalchemy import asc, delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.dataset import DatasetTable
from cipher.schemas.dataset import (
    Dataset,
    DatasetCreate,
    DatasetSortField,
    DatasetsRequest,
    DatasetUpdate,
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
        """Query datasets with filtering, pagination, and sorting."""
        if isinstance(request, dict):
            request = DatasetsRequest(**request)
        elif request is None:
            request = DatasetsRequest()

        # Build where clause
        where_clause = []
        if request.query:
            where_clause.append(
                or_(
                    DatasetTable.name.ilike(f"%{request.query}%"),
                    DatasetTable.description.ilike(f"%{request.query}%"),
                )
            )

        # Count query
        count_stmt = select(func.count(DatasetTable.id))
        if where_clause:
            count_stmt = count_stmt.where(*where_clause)

        count_result = await self.session.execute(count_stmt)
        total_count = count_result.scalar_one()

        # Data query
        data_stmt = select(DatasetTable)
        if where_clause:
            data_stmt = data_stmt.where(*where_clause)

        # Sorting
        if request.sort_by:
            sort_column = {
                DatasetSortField.NAME: DatasetTable.name,
                DatasetSortField.DATE_CREATED: DatasetTable.date_created,
                DatasetSortField.DATE_LAST_UPDATED: DatasetTable.date_last_updated,
            }[to_snake(request.sort_by)]

            if request.sort_order == SortOrder.DESC:
                data_stmt = data_stmt.order_by(desc(sort_column))
            else:
                data_stmt = data_stmt.order_by(asc(sort_column))

        # Pagination
        data_stmt = data_stmt.offset((request.page - 1) * request.limit).limit(
            request.limit
        )

        data_result = await self.session.execute(data_stmt)
        datasets = [Dataset.model_validate(ds) for ds in data_result.scalars().all()]

        total_pages = (total_count + request.limit - 1) // request.limit

        return PaginatedDatasetsResponse(
            total=total_count,
            page=request.page,
            limit=request.limit,
            total_pages=total_pages,
            data=datasets,
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
