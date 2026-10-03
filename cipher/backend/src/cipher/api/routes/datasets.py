from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from cipher.api.deps.access import DatasetAccessDep, DatasetIdDep
from cipher.api.deps.authentication import AdminOnly
from cipher.api.deps.elasticsearch import TextChunkDatastoreDep
from cipher.api.deps.postgres import (
    CommentDatastoreDep,
    DatasetDatastoreDep,
    EnrichmentDatastoreDep,
    EnrichmentRunDatastoreDep,
    FileDatastoreDep,
    UserDatastoreDep,
)
from cipher.api.services.enrichment_estimator import build_dataset_estimates
from cipher.schemas.ingestion.dataset import (
    Dataset,
    DatasetCreate,
    DatasetPublic,
    DatasetsRequest,
    DatasetStagingSummary,
    DatasetStatsRequest,
    DatasetStatsResponse,
    DatasetUpdate,
    PaginatedDatasetsResponse,
)
from cipher.schemas.ingestion.estimation import DatasetEnrichmentEstimates, RunDevice
from cipher.schemas.ingestion.file import FileBrowserRequest, FileBrowserResponse
from cipher.schemas.ingestion.user import User
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
    dependencies=[AdminOnly],
)
async def create_dataset(dataset: DatasetCreate, datastore: DatasetDatastoreDep) -> Dataset:
    """Admin: create a new dataset (everyone else files a dataset request)."""
    return await datastore.add_dataset(dataset)


@router.get(
    "/{id}",
    summary="Get dataset by ID",
    response_model=DatasetPublic,
    response_model_by_alias=True,
)
async def get_dataset_by_id(id: str, access: DatasetAccessDep, datastore: DatasetDatastoreDep) -> DatasetPublic:
    """A dataset you're a member of, or a discoverable one (with `hasAccess=false`, nothing else opens)."""
    dataset = await datastore.get_dataset_by_id(dataset_id=id)
    has_access = access.allows(id)
    if dataset is None or not (has_access or dataset.is_discoverable):
        access.require(id)
        raise HTTPException(status_code=404, detail=f"Dataset not found: {id}")
    return DatasetPublic(**dataset.model_dump(), has_access=has_access)


@router.get(
    "",
    summary="Get all datasets",
    response_model=PaginatedDatasetsResponse,
    response_model_by_alias=True,
)
async def get_datasets(
    params: Annotated[DatasetsRequest, Depends()], access: DatasetAccessDep, datastore: DatasetDatastoreDep
):
    """Datasets you're a member of plus discoverable ones (`hasAccess` tells them apart), paginated."""
    return await datastore.get_datasets(request=params, accessible_ids=access.dataset_ids)


@router.get(
    "/{id}/users",
    summary="List a dataset's members",
    response_model=list[User],
    response_model_by_alias=True,
    dependencies=[AdminOnly],
)
async def get_dataset_users(id: DatasetIdDep, user_datastore: UserDatastoreDep) -> list[User]:
    """Admin: users with explicit membership in a dataset (admins can see it too, without being listed)."""
    return await user_datastore.get_dataset_users(dataset_id=id)


@router.get(
    "/{id}/stats",
    summary="Get aggregate file stats for a dataset",
    response_model=DatasetStatsResponse,
    response_model_by_alias=True,
)
async def get_dataset_stats(
    id: DatasetIdDep,
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
async def get_dataset_staging(id: DatasetIdDep, datastore: DatasetDatastoreDep):
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
    id: DatasetIdDep,
    dataset_datastore: DatasetDatastoreDep,
    file_datastore: FileDatastoreDep,
    enrichment_datastore: EnrichmentDatastoreDep,
    run_datastore: EnrichmentRunDatastoreDep,
    accelerator: RunDevice = RunDevice.CUDA,
):
    """Per-enrichment ETA from the staged inventory + measured throughput, each on the device it runs on.

    `accelerator` only applies to analytics that accept `--device` (text/image embedding, face detection).
    """
    if await dataset_datastore.get_dataset_by_id(dataset_id=id) is None:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {id}")
    return await build_dataset_estimates(
        dataset_id=id,
        accelerator=accelerator,
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
    id: DatasetIdDep,
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
    dependencies=[AdminOnly],
)
async def delete_dataset(
    id: str,
    datastore: DatasetDatastoreDep,
    enrichment_datastore: EnrichmentDatastoreDep,
    comment_datastore: CommentDatastoreDep,
    text_chunk_datastore: TextChunkDatastoreDep,
) -> bool:
    """Admin: delete a dataset and everything scoped to it.

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


@router.put("/{id}", summary="Add or update a dataset", response_model=Dataset, dependencies=[AdminOnly])
async def update_dataset(id: str, data: DatasetUpdate, datastore: DatasetDatastoreDep) -> Dataset:
    """Admin: add or update a dataset."""
    logger.info(f"Updating dataset {id} with data: {data}")
    return await datastore.update_dataset(dataset_id=id, data=data)
