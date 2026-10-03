"""File dataset and enrichment requests as GitHub issues.

Registered before ``datasets.router`` so ``/datasets/requests`` is matched
here rather than by ``GET /datasets/{id}``.
"""

from fastapi import APIRouter, HTTPException

from cipher.api.deps.access import DatasetAccessDep
from cipher.api.deps.authentication import CurrentUserDep
from cipher.api.deps.github import GithubClientDep, OptionalGithubClientDep
from cipher.api.deps.postgres import (
    DatasetDatastoreDep,
    EnrichmentDatastoreDep,
    EnrichmentRunDatastoreDep,
    FileDatastoreDep,
)
from cipher.api.services.enrichment_estimator import build_dataset_estimates
from cipher.schemas.ingestion.dataset_request import (
    DatasetRequest,
    DatasetRequestConfig,
    DatasetRequestResult,
    EnrichmentRequest,
    EnrichmentRequestResult,
)
from cipher.schemas.ingestion.estimation import DatasetEnrichmentEstimates, format_duration, total_estimate_seconds

router = APIRouter(
    prefix="/datasets/requests",
    tags=["dataset-requests"],
    responses={418: {"description": "I'm a teapot"}},
)


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

    lines += ["", "---", "_Filed via the Cipher dataset request form._"]
    return "\n".join(lines)


@router.get(
    "",
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
    "",
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

    lines += ["", "---", "_Filed from the Cipher dataset page._"]
    return "\n".join(lines)


@router.post(
    "/enrichments",
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
