from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from cipher.api.deps.access import DatasetAccessDep, DatasetIdDep
from cipher.api.deps.authentication import AdminOnly, CurrentUserDep
from cipher.api.deps.elasticsearch import TextChunkDatastoreDep
from cipher.api.deps.github import GithubClientDep, OptionalGithubClientDep
from cipher.api.deps.postgres import (
    CommentDatastoreDep,
    DatasetDatastoreDep,
    DatasetProfileDatastoreDep,
    EnrichmentDatastoreDep,
    EnrichmentRunDatastoreDep,
    FileDatastoreDep,
    UserDatastoreDep,
    end_transactions,
)
from cipher.api.services.enrichment_estimator import build_dataset_estimates
from cipher.api.services.search_assist import brief as write_brief
from cipher.schemas._base.exceptions import EntityNotFoundError
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
from cipher.schemas.ingestion.dataset_profile import DatasetProfile
from cipher.schemas.ingestion.dataset_request import (
    ANALYTIC_COMMANDS,
    AnalyticRequest,
    DatasetRequest,
    DatasetRequestConfig,
    DatasetRequestResult,
    EnrichmentRequest,
    EnrichmentRequestResult,
)
from cipher.schemas.ingestion.estimation import (
    ESTIMATE_ORDER,
    DatasetEnrichmentEstimates,
    RunDevice,
    format_duration,
    total_estimate_seconds,
)
from cipher.schemas.ingestion.file import FileBrowserRequest, FileBrowserResponse
from cipher.schemas.ingestion.user import User
from cipher.schemas.interaction.comment import CommentableType
from cipher.schemas.interaction.global_search import DatasetBrief

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


# Briefs for multi-dataset selections (in memory, lost on restart); a single dataset's is saved on its profile row.
_merged_briefs: dict[tuple[str, ...], DatasetBrief] = {}


async def _brief(access, datastore, dataset_ids: list[str] | None, *, regenerate: bool) -> DatasetBrief:
    profile = await datastore.get_merged(dataset_ids=access.scope(dataset_ids))
    if profile.file_count == 0:
        raise HTTPException(status_code=404, detail="No profiled files to summarize")
    single = profile.dataset_ids[0] if len(profile.dataset_ids) == 1 else None
    key = tuple(profile.dataset_ids)
    cached = (await datastore.get_brief(single) if single else _merged_briefs.get(key)) if not regenerate else None
    if cached is None:
        await end_transactions(datastore)
        try:
            cached = (await write_brief(profile)).model_copy(update={"date_generated": datetime.now(UTC)})
        except Exception as exc:  # noqa: BLE001 -- any model/provider failure is the same "AI unavailable" to the page
            logger.exception(exc)
            raise HTTPException(status_code=503, detail="The AI model is unavailable right now.") from exc
        if single:
            await datastore.save_brief(single, cached.model_dump(mode="json"))
        else:
            _merged_briefs[key] = cached
    brief = DatasetBrief.model_validate(cached)
    is_outdated = bool(brief.date_generated and profile.date_computed and profile.date_computed > brief.date_generated)
    return brief.model_copy(update={"is_outdated": is_outdated})


# -- requests: filed as GitHub issues for an admin to act on. Declared before `/{id}` so
#    `/datasets/requests` isn't read as a dataset id.


def _commands_block(analytics: list[AnalyticRequest], *, dataset_id: str) -> list[str]:
    """The requested analytics as `cipher` commands, prerequisites first, ready to paste."""
    ordered = sorted(
        (a for a in analytics if a.enrichment_type in ANALYTIC_COMMANDS),
        key=lambda a: (
            ESTIMATE_ORDER.index(a.enrichment_type) if a.enrichment_type in ESTIMATE_ORDER else len(ESTIMATE_ORDER)
        ),
    )
    if not ordered:
        return []
    return ["", "### Commands", "", "```bash", *(a.command(dataset_id=dataset_id) for a in ordered), "```"]


def _render_issue_body(*, request: DatasetRequest, requester: str) -> str:
    """Render the issue body.

    Analytics are a wishlist for whoever ingests the dataset, not a run
    trigger -- there's no file inventory yet to size a time estimate against,
    so none is attempted here (see `docs/enrichments.md`).
    """
    lines = [
        "### Dataset request",
        "",
        f"- **Name:** {request.name}",
        f"- **Dataset ID:** `{request.dataset_id}`",
        f"- **Requested by:** {requester}",
        "",
        "### Description",
        "",
        request.description.strip() if request.description else "_None provided._",
        "",
        "### Analytics wanted once ingested",
        "",
    ]
    if not request.analytics:
        lines.append("_None specified._")
    for analytic in request.analytics:
        lines.append(f"- **{analytic.enrichment_type.value}**")
        for key, value in analytic.parameters.items():
            lines.append(f"  - `{key}`: `{value}`")
    lines += _commands_block(request.analytics, dataset_id=request.dataset_id)

    lines += ["", "---", "_Filed via the Cipher dataset request form._"]
    return "\n".join(lines)


@router.get(
    "/requests",
    summary="Whether dataset requests are configured, and where issues are filed",
    response_model=DatasetRequestConfig,
    response_model_by_alias=True,
)
async def get_dataset_request_config(client: OptionalGithubClientDep) -> DatasetRequestConfig:
    """Report the target repo + issues link, or `configured=False` if GitHub isn't set up."""
    if client is None:
        return DatasetRequestConfig(configured=False)
    return DatasetRequestConfig(configured=True, repo=client.repo, issues_url=client.issues_url)


@router.post(
    "/requests",
    summary="File a dataset request as a GitHub issue",
    response_model=DatasetRequestResult,
    response_model_by_alias=True,
)
async def create_dataset_request(
    request: DatasetRequest, user: CurrentUserDep, client: GithubClientDep
) -> DatasetRequestResult:
    """Create a GitHub issue for a dataset request and return its number/URL."""
    requester = f"{user.name} <{user.email}>" if user.email else user.name
    issue = await client.create_issue(
        title=f"Dataset request: {request.name}",
        body=_render_issue_body(request=request, requester=requester),
    )
    return DatasetRequestResult(
        issue_number=issue["number"],
        issue_url=issue["html_url"],
        issues_url=client.issues_url,
    )


def _render_enrichment_body(
    *, request: EnrichmentRequest, dataset_name: str, requester: str, estimates: DatasetEnrichmentEstimates
) -> str:
    """Render an enrichment request, quoting each analytic's current progress and ETA."""
    by_type = {item.enrichment_type: item for item in estimates.items}
    lines = [
        "### Enrichment request",
        "",
        f"- **Dataset:** {dataset_name} (`{request.dataset_id}`)",
        f"- **Requested by:** {requester}",
        "",
        "### Why",
        "",
        request.note.strip() if request.note else "_None provided._",
        "",
        "### Analytics",
        "",
        "| Analytic | Device | Eligible | Done | Estimate |",
        "|---|---|---|---|---|",
    ]
    for analytic in request.analytics:
        estimate = by_type.get(analytic.enrichment_type)
        if estimate is None:
            lines.append(f"| `{analytic.enrichment_type.value}` | | | | |")
            continue
        eligible = (
            f"{estimate.eligible.unit_count} {estimate.eligible.unit.value}" if estimate.eligible.estimable else "n/a"
        )
        eta = format_duration(estimate.estimate_seconds) if estimate.estimate_seconds is not None else estimate.basis
        lines.append(
            f"| `{analytic.enrichment_type.value}` | {estimate.device.value} | {eligible} "
            f"| {round(estimate.progress * 100)}% | {eta} |"
        )
    requested = [by_type[a.enrichment_type] for a in request.analytics if a.enrichment_type in by_type]
    lines += ["", f"**Total (sequential):** {format_duration(total_estimate_seconds(requested))}"]

    tuned = [a for a in request.analytics if a.parameters]
    if tuned:
        lines += ["", "### Parameters", ""]
        for analytic in tuned:
            lines.append(f"- **{analytic.enrichment_type.value}**")
            lines += [f"  - `{key}`: `{value}`" for key, value in analytic.parameters.items()]
    lines += _commands_block(request.analytics, dataset_id=request.dataset_id)

    lines += ["", "---", "_Filed from the Cipher dataset page._"]
    return "\n".join(lines)


@router.post(
    "/requests/enrichments",
    summary="Request more analytics on a loaded dataset",
    response_model=EnrichmentRequestResult,
    response_model_by_alias=True,
)
async def create_enrichment_request(
    request: EnrichmentRequest,
    access: DatasetAccessDep,
    client: OptionalGithubClientDep,
    dataset_datastore: DatasetDatastoreDep,
    file_datastore: FileDatastoreDep,
    enrichment_datastore: EnrichmentDatastoreDep,
    run_datastore: EnrichmentRunDatastoreDep,
) -> EnrichmentRequestResult:
    """Render the request as a GitHub issue; file it when GitHub is configured, else return it to copy."""
    access.require(request.dataset_id)
    user = access.user
    dataset = await dataset_datastore.get_dataset_by_id(dataset_id=request.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {request.dataset_id}")
    estimates = await build_dataset_estimates(
        dataset_id=request.dataset_id,
        dataset_repo=dataset_datastore,
        file_repo=file_datastore,
        enrichment_repo=enrichment_datastore,
        run_repo=run_datastore,
        only=[a.enrichment_type for a in request.analytics],
        params_by_type={a.enrichment_type: a.parameters for a in request.analytics},
    )
    requester = f"{user.name} <{user.email}>" if user.email else user.name
    title = f"Enrichment request: {dataset.name}"
    body = _render_enrichment_body(request=request, dataset_name=dataset.name, requester=requester, estimates=estimates)
    if client is None:
        return EnrichmentRequestResult(title=title, body=body)
    issue = await client.create_issue(title=title, body=body)
    return EnrichmentRequestResult(title=title, body=body, issue_number=issue["number"], issue_url=issue["html_url"])


@router.get(
    "/profile/brief",
    summary="AI summary of what's in these datasets, plus starting searches",
    response_model=DatasetBrief,
    response_model_by_alias=True,
)
async def get_dataset_brief(
    access: DatasetAccessDep,
    datastore: DatasetProfileDatastoreDep,
    dataset_ids: Annotated[list[str] | None, Query(alias="datasetIds")] = None,
) -> DatasetBrief:
    """From the precomputed profile only (no file contents); written once, then saved until regenerated."""
    return await _brief(access, datastore, dataset_ids, regenerate=False)


@router.post(
    "/profile/brief",
    summary="Write a fresh AI summary of these datasets, replacing the saved one",
    response_model=DatasetBrief,
    response_model_by_alias=True,
)
async def regenerate_dataset_brief(
    access: DatasetAccessDep,
    datastore: DatasetProfileDatastoreDep,
    dataset_ids: Annotated[list[str] | None, Query(alias="datasetIds")] = None,
) -> DatasetBrief:
    """Re-read the current profile; the saved summary otherwise survives profile recomputes."""
    return await _brief(access, datastore, dataset_ids, regenerate=True)


@router.get(
    "/profile",
    summary="What's in these datasets: composition, timeline, key people and places (the search briefing)",
    response_model=DatasetProfile,
    response_model_by_alias=True,
)
async def get_dataset_profile(
    access: DatasetAccessDep,
    datastore: DatasetProfileDatastoreDep,
    dataset_ids: Annotated[list[str] | None, Query(alias="datasetIds")] = None,
) -> DatasetProfile:
    """Merged precomputed profiles; datasets never profiled are listed in `unprofiledDatasetIds`."""
    return await datastore.get_merged(dataset_ids=access.scope(dataset_ids))


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
        raise EntityNotFoundError(entity_name="Dataset", identifier=id)
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
