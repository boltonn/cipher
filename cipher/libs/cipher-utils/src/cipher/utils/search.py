"""Global search configuration (`SEARCH__*`), shared by the API and the orchestration CLI. See docs/global-search.md."""

from pydantic import BaseModel, Field


class SearchConfig(BaseModel):
    """Global search (`SEARCH__*`)."""

    lane_budget_ms: int = Field(1_000, description="Per-lane time budget on /search/overview; a slower lane times out")
    history_retention_days: int = Field(14, description="Unsaved searches older than this are pruned")
