"""File a dataset request as a GitHub issue.

Registered before ``datasets.router`` so ``/datasets/requests`` is matched
here rather than by ``GET /datasets/{id}``.
"""

from fastapi import APIRouter

from cipher.api.deps.authentication import CurrentUserDep
from cipher.api.deps.github import GithubClientDep, OptionalGithubClientDep
from cipher.schemas.ingestion.dataset_request import (
    DatasetRequest,
    DatasetRequestConfig,
    DatasetRequestResult,
)

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
