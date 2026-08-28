"""GitHub issue client, wired from the ``GITHUB__*`` settings block."""

from typing import Annotated
from urllib.parse import quote_plus

import httpx
from fastapi import Depends, HTTPException

from cipher.api.settings import GithubConfig, Settings

settings = Settings()


class GithubIssueClient:
    """Thin async wrapper over the GitHub REST issues API."""

    def __init__(self, config: GithubConfig) -> None:
        self._config = config

    @property
    def repo(self) -> str:
        """The ``owner/repo`` that receives dataset-request issues."""
        return self._config.repo

    @property
    def issues_url(self) -> str:
        """A github.com search URL for open dataset-request issues (for thumbs-up)."""
        query = "is:issue state:open"
        if self._config.labels:
            query += f" label:{self._config.labels[0]}"
        return f"https://github.com/{self._config.repo}/issues?q={quote_plus(query)}"

    async def create_issue(self, *, title: str, body: str) -> dict:
        """Create an issue in the configured repo, applying labels and issue type."""
        payload: dict = {"title": title, "body": body}
        if self._config.labels:
            payload["labels"] = self._config.labels
        if self._config.issue_type:
            payload["type"] = self._config.issue_type

        url = f"{self._config.api_base.rstrip('/')}/repos/{self._config.repo}/issues"
        headers = {
            "Authorization": f"Bearer {self._config.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code >= 300:
            raise HTTPException(
                status_code=502,
                detail=f"GitHub issue creation failed ({response.status_code}): {response.text}",
            )
        return response.json()


def get_github_client() -> GithubIssueClient:
    """Provide a GitHub issue client, or 503 if the integration is unconfigured."""
    if settings.github is None:
        raise HTTPException(status_code=503, detail="GitHub integration is not configured")
    return GithubIssueClient(settings.github)


GithubClientDep = Annotated[GithubIssueClient, Depends(get_github_client)]
