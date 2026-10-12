"""Dataset profile: the precomputed "what's in here" summary behind the empty-query search briefing.

See docs/global-search.md §6.
"""

from datetime import datetime

from pydantic import Field

from cipher.schemas._base.base import BaseModel
from cipher.schemas.content.results import MonthCount

DEFAULT_BULK_SOURCE_TAGS = ("promotions", "updates", "social", "forums")
"""Source categories (Gmail's) treated as bulk mail when ranking who's in a dataset."""
DEFAULT_BULK_MESSAGE_STATES = ("spam",)
PROFILE_VERSION = 1
"""Bump when the computation changes, so cached briefs are regenerated."""


class ProfileEntity(BaseModel):
    """An entity ranked in a profile, by how many (non-bulk) files mention it."""

    entity_id: str
    display_name: str
    entity_type: str
    files: int = Field(description="Distinct non-bulk files with a mention of it")


class ProfileCorrespondent(BaseModel):
    """A directed `emailed` edge and how many emails went that way."""

    src_entity_id: str
    src_name: str
    dst_entity_id: str
    dst_name: str
    emails: int


class DatasetProfile(BaseModel):
    """One dataset's profile, or several merged (counts summed, top lists re-ranked).

    Top lists are each dataset's top 200, so a merged list is exact for anything
    in at least one dataset's top 200 and approximate in the long tail.
    """

    dataset_ids: list[str]
    file_count: int = 0
    chunk_count: int = 0
    filetype_group_counts: dict[str, int] = Field(default_factory=dict)
    language_counts: dict[str, int] = Field(default_factory=dict, description="Empty until chunk language is set")
    date_histogram: list[MonthCount] = Field(default_factory=list, description="Files per month, by content date")
    top_people_orgs: list[ProfileEntity] = Field(default_factory=list)
    top_selectors: list[ProfileEntity] = Field(default_factory=list)
    top_places: list[ProfileEntity] = Field(default_factory=list)
    top_correspondents: list[ProfileCorrespondent] = Field(default_factory=list)
    image_sample_ids: list[str] = Field(default_factory=list)
    unprofiled_dataset_ids: list[str] = Field(
        default_factory=list, description="Requested datasets with no profile yet (run `cipher profile-dataset`)"
    )
    date_computed: datetime | None = Field(default=None, description="Oldest profile in the merge")
