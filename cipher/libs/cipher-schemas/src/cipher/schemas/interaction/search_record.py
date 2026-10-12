"""Search records: a stored question (query, datasets, filters), never its results.

Private to the user who ran it (admins can read any). See docs/global-search.md §7.
"""

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta

from pydantic import Field

from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import PaginatedResponse


class SearchFilters(BaseModel):
    """Filter chips added on the search page; they AND together across every lane."""

    entity_ids: list[str] = Field(default_factory=list)
    entity_groups: list[list[str]] = Field(
        default_factory=list,
        description="Each group is one person/thing the user picked several entities for (spellings, stubs, "
        "addresses): content must mention at least one of every group",
    )
    filetype_groups: list[str] = Field(default_factory=list)
    date_from: date | None = Field(default=None, description="Content dated on or after this day")
    date_to: date | None = Field(default=None, description="Content dated on or before this day")
    exact_match: bool = Field(default=False, description="Text results must contain the query as an exact phrase")

    def datetime_range(self) -> tuple[datetime | None, datetime | None]:
        """The day range as UTC datetimes, `to` exclusive (the start of the day after `date_to`)."""
        start = datetime.combine(self.date_from, time.min, tzinfo=UTC) if self.date_from else None
        end = datetime.combine(self.date_to + timedelta(days=1), time.min, tzinfo=UTC) if self.date_to else None
        return start, end


class SearchRequest(BaseModel):
    """What the user asked: the part of a search that is stored and re-run."""

    query: str = Field(default="", max_length=1_000)
    dataset_ids: list[str] = Field(default_factory=list, description="Empty = every dataset the user can access")
    filters: SearchFilters = Field(default_factory=SearchFilters)
    parent_id: str | None = Field(default=None, description="The search this one was narrowed from")

    def fingerprint(self, *, user_id: str) -> str:
        """Same user + same question = same record (case/whitespace-insensitive query, order-free lists)."""
        filters = self.filters.model_dump(
            mode="json", exclude={"exact_match"} if not self.filters.exact_match else None
        )
        canonical = {
            "user_id": user_id,
            "query": " ".join(self.query.lower().split()),
            "dataset_ids": sorted(self.dataset_ids),
            "filters": {
                key: sorted(sorted(v) if isinstance(v, list) else v for v in value)
                if isinstance(value, list)
                else value
                for key, value in filters.items()
            },
        }
        return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


class SearchRecord(SearchRequest):
    """A stored search."""

    id: str
    user_id: str
    run_count: int
    name: str | None = None
    date_created: datetime
    date_last_run: datetime
    date_saved: datetime | None = None


class SaveSearchRequest(BaseModel):
    """Keep a search past pruning, under an optional name."""

    name: str | None = Field(default=None, max_length=255)


class PaginatedSearchHistory(PaginatedResponse):
    """A page of the user's searches, most recently run first."""

    data: list[SearchRecord]
