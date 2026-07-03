"""File ingestion workflow - orchestrates loading and analysis."""

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresDatasetRepository,
    PostgresFileRepository,
)
from cipher.schemas.dataset import Dataset, DatasetCreate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def create_dataset(
    session: "AsyncSession",
    name: str,
    description: str | None = None,
) -> Dataset:
    """Create a new dataset and return it."""
    dataset_repo = PostgresDatasetRepository(session=session)
    dataset_create = DatasetCreate(name=name, description=description)
    dataset = await dataset_repo.add_dataset(dataset=dataset_create)
    await session.commit()
    logger.success(f"Created dataset: {dataset.name} (ID: {dataset.id})")
    return dataset


async def get_dataset(
    session: "AsyncSession",
    dataset_id: str,
) -> Dataset | None:
    """Retrieve an existing dataset by ID."""
    dataset_repo = PostgresDatasetRepository(session=session)
    return await dataset_repo.get_dataset_by_id(dataset_id=dataset_id)


async def load_files(
    session: "AsyncSession",
    path: Path,
    dataset_id: str,
    file_analyzer: Callable,
    limit: int | None = None,
    batch_size: int = 100,
) -> int:
    """Load files from path into dataset, returning the number of files loaded."""
    if not path.exists():
        raise ValueError(f"Path does not exist: {path}")

    file_repo = PostgresFileRepository(session=session)

    batch = []
    total_processed = 0

    for file_create in tqdm(file_analyzer(path, dataset_id, limit), desc="Processing files"):
        batch.append(file_create)

        if len(batch) >= batch_size:
            for f in batch:
                await file_repo.upsert_file(f)
            await session.flush()
            total_processed += len(batch)
            batch = []

    if batch:
        for f in batch:
            await file_repo.upsert_file(f)
        total_processed += len(batch)

    await session.commit()
    logger.success(f"Loaded {total_processed} files into dataset {dataset_id}")
    return total_processed


async def load_files_workflow(
    session: "AsyncSession",
    path: Path,
    file_analyzer: Callable,
    dataset_id: str | None = None,
    dataset_name: str | None = None,
    dataset_desc: str | None = None,
    limit: int | None = None,
    batch_size: int = 100,
) -> str:
    """Full ingestion workflow: create/validate dataset, then load files.

    Returns the dataset ID as a string.
    """
    if dataset_id is None:
        assert dataset_name is not None, (
            "Dataset name is required when creating a new dataset"
        )
        dataset = await create_dataset(
            session=session, name=dataset_name, description=dataset_desc
        )
        dataset_id = str(dataset.id)
    else:
        dataset = await get_dataset(session=session, dataset_id=dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")
        logger.info(f"Using existing dataset: {dataset.name}")

    await load_files(
        session=session,
        path=path,
        dataset_id=dataset_id,
        file_analyzer=file_analyzer,
        limit=limit,
        batch_size=batch_size,
    )

    return dataset_id
