from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from cipher.api.deps.postgres import DatasetDatastoreDep
from cipher.schemas.dataset import (
    Dataset,
    DatasetCreate,
    DatasetsRequest,
    DatasetStatsRequest,
    DatasetStatsResponse,
    DatasetUpdate,
    PaginatedDatasetsResponse,
)

router = APIRouter(
    prefix="/datasets",
    tags=["datasets"],
    responses={418: {"description": "I'm a teapot"}},
)


@router.post(
    "",
    summary="Create a new dataset",
    response_model=Dataset,
    response_model_by_alias=True,
)
async def create_dataset(
    dataset: DatasetCreate, datastore: DatasetDatastoreDep
) -> Dataset:
    """Create a new dataset."""
    return await datastore.add_dataset(dataset)


@router.get(
    "/{id}",
    summary="Get dataset by ID",
    response_model=Dataset,
    response_model_by_alias=True,
)
async def get_dataset_by_id(id: str, datastore: DatasetDatastoreDep):
    """Get a single dataset by its ID."""
    dataset = await datastore.get_dataset_by_id(dataset_id=id)
    if dataset is None:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {id}")
    return dataset


@router.get(
    "",
    summary="Get all datasets",
    response_model=PaginatedDatasetsResponse,
    response_model_by_alias=True,
)
async def get_datasets(
    params: Annotated[DatasetsRequest, Depends()], datastore: DatasetDatastoreDep
):
    """Get all datasets, optionally filtered by a search query, with pagination."""
    return await datastore.get_datasets(request=params)


@router.get(
    "/{id}/stats",
    summary="Get aggregate file stats for a dataset",
    response_model=DatasetStatsResponse,
    response_model_by_alias=True,
)
async def get_dataset_stats(
    id: str,
    params: Annotated[DatasetStatsRequest, Depends()],
    datastore: DatasetDatastoreDep,
):
    """Get a dataset's file stats: totals, filetype breakdowns, and a load-time histogram."""
    if await datastore.get_dataset_by_id(dataset_id=id) is None:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {id}")
    return await datastore.get_dataset_stats(dataset_id=id, request=params)


@router.delete(
    "/{id}",
    summary="Delete dataset by ID",
    response_model=bool,
    response_model_by_alias=True,
)
async def delete_dataset(id: str, datastore: DatasetDatastoreDep) -> bool:
    """Delete a dataset by its ID."""
    return await datastore.delete_dataset(dataset_id=id)


@router.put("/{id}", summary="Add or update a dataset", response_model=Dataset)
async def update_dataset(
    id: str, data: DatasetUpdate, datastore: DatasetDatastoreDep
) -> Dataset:
    """Add or update a dataset."""
    logger.info(f"Updating dataset {id} with data: {data}")
    return await datastore.update_dataset(dataset_id=id, data=data)
