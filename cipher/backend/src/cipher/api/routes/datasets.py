from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from cipher.api.deps.elasticsearch import TextChunkDatastoreDep
from cipher.api.deps.postgres import (
    CommentDatastoreDep,
    DatasetDatastoreDep,
    EnrichmentDatastoreDep,
    EnrichmentRunDatastoreDep,
    FileDatastoreDep,
)
from cipher.api.services.enrichment_estimator import build_dataset_estimates
from cipher.schemas.ingestion.dataset import (
    Dataset,
    DatasetCreate,
    DatasetsRequest,
    DatasetStagingSummary,
    DatasetStatsRequest,
    DatasetStatsResponse,
    DatasetUpdate,
    PaginatedDatasetsResponse,
)
from cipher.schemas.ingestion.estimation import DatasetEnrichmentEstimates, RunDevice
from cipher.schemas.ingestion.file import FileBrowserRequest, FileBrowserResponse
from cipher.schemas.interaction.comment import CommentableType

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


@router.get(
    "/{id}/staging",
    summary="Whether a dataset has finished staging, plus its filetype inventory",
    response_model=DatasetStagingSummary,
    response_model_by_alias=True,
)
async def get_dataset_staging(id: str, datastore: DatasetDatastoreDep):
    """Staging status + per-`filetype_group` counts/sizes -- the basis for enrichment estimates."""
    if await datastore.get_dataset_by_id(dataset_id=id) is None:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {id}")
    return await datastore.get_staging_summary(dataset_id=id)


@router.get(
    "/{id}/enrichment-estimates",
    summary="Rough wall-time estimate per enrichment for a dataset",
    response_model=DatasetEnrichmentEstimates,
    response_model_by_alias=True,
)
async def get_dataset_enrichment_estimates(
    id: str,
    dataset_datastore: DatasetDatastoreDep,
    file_datastore: FileDatastoreDep,
    enrichment_datastore: EnrichmentDatastoreDep,
    run_datastore: EnrichmentRunDatastoreDep,
    device: RunDevice = RunDevice.CPU,
):
    """Per-enrichment ETA from the staged inventory + measured throughput, for the request wizard."""
    if await dataset_datastore.get_dataset_by_id(dataset_id=id) is None:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {id}")
    return await build_dataset_estimates(
        dataset_id=id,
        device=device,
        dataset_repo=dataset_datastore,
        file_repo=file_datastore,
        enrichment_repo=enrichment_datastore,
        run_repo=run_datastore,
    )


@router.get(
    "/{id}/browse",
    summary="Browse a dataset's files and folders",
    response_model=FileBrowserResponse,
    response_model_by_alias=True,
)
async def browse_dataset_files(
    id: str,
    params: Annotated[FileBrowserRequest, Depends()],
    dataset_datastore: DatasetDatastoreDep,
    file_datastore: FileDatastoreDep,
):
    """Browse a dataset's files, optionally scoped to a folder path, paginated (max 100 entries per page)."""
    if await dataset_datastore.get_dataset_by_id(dataset_id=id) is None:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {id}")
    return await file_datastore.browse_directory(dataset_id=id, req=params)


@router.delete(
    "/{id}",
    summary="Delete dataset by ID",
    response_model=bool,
    response_model_by_alias=True,
)
async def delete_dataset(
    id: str,
    datastore: DatasetDatastoreDep,
    enrichment_datastore: EnrichmentDatastoreDep,
    comment_datastore: CommentDatastoreDep,
    text_chunk_datastore: TextChunkDatastoreDep,
) -> bool:
    """Delete a dataset and everything scoped to it.

    Most child records (files, extracted text, images, faces) cascade via
    FK when the dataset row goes. Enrichment and comment rows don't -- both
    reference their parent polymorphically (no real FK, since either can
    point at files, messages, faces, persons, etc.) -- and Elasticsearch
    chunks live in a separate datastore entirely. All three are purged
    explicitly here first so nothing is left orphaned.
    """
    deleted_enrichments = await enrichment_datastore.delete_by_dataset_files(dataset_id=id)
    deleted_comments = await comment_datastore.delete_by_commentable(
        commentable_type=CommentableType.DATASET, commentable_id=id
    )
    deleted_chunks = await text_chunk_datastore.delete_by_dataset_id(dataset_id=id)
    logger.info(
        f"Purged {deleted_enrichments} enrichments, {deleted_comments} comments, "
        f"{deleted_chunks} search chunks for dataset {id} before delete"
    )
    return await datastore.delete_dataset(dataset_id=id)


@router.put("/{id}", summary="Add or update a dataset", response_model=Dataset)
async def update_dataset(
    id: str, data: DatasetUpdate, datastore: DatasetDatastoreDep
) -> Dataset:
    """Add or update a dataset."""
    logger.info(f"Updating dataset {id} with data: {data}")
    return await datastore.update_dataset(dataset_id=id, data=data)
