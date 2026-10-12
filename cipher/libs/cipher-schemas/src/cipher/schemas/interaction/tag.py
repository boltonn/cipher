"""Tags: who or what put a tag on something, and when.

`tag` is the source of truth. The `tags` / `negative_tags` / `tag_scores`
columns on `image`, `file`, `entity` and `event` are read copies kept in sync by the tag
repository, so filtering and display never pay for the provenance.
"""

from datetime import datetime

from pydantic import Field

from cipher.schemas._base.base import BaseModel, StrEnum
from cipher.schemas._base.common import ModelTagType


class TagTargetType(StrEnum):
    """What a tag is on.

    `content` is file bytes, keyed by `sha256` -- every copy of a file (and its `image`
    row) shares one set of tags. `entity` covers every entity type (person, organization,
    location, selector); person and location records mirror their entity's tags.
    """

    CONTENT = "content"
    ENTITY = "entity"
    EVENT = "event"


class TagSourceType(StrEnum):
    """Who or what made a tag decision."""

    USER = "user"
    MODEL = "model"


UNKNOWN_TAG_SOURCE = "unknown"
"""`source_name` for tags that existed before provenance was recorded."""


class TagSource(BaseModel):
    """Who or what is making a tag decision: a user (by id) or a model (by name/version)."""

    type: TagSourceType
    name: str

    @classmethod
    def user(cls, user_id: str) -> "TagSource":
        """A signed-in user's decision."""
        return cls(type=TagSourceType.USER, name=user_id)

    @classmethod
    def model(cls, name: str) -> "TagSource":
        """A model's decision, e.g. `clip:ViT-B-32` or an LLM id."""
        return cls(type=TagSourceType.MODEL, name=name)


class Tag(BaseModel):
    """One source's decision about one tag on one target."""

    id: str
    target_type: TagTargetType
    target_id: str = Field(description="sha256 for content; the entity / event id otherwise")
    tag: str
    label: ModelTagType | None = Field(default=None, description="positive / negative; null for a score only")
    score: float | None = Field(default=None, ge=0, le=1, description="A model's confidence the tag applies")
    source_type: TagSourceType
    source_name: str = Field(description="User id for a user; model name/version for a model")
    date_updated: datetime


class TagLabelAuthorsRequest(BaseModel):
    """Which other users labelled `tag` on these targets (asked before clearing it in bulk)."""

    target_type: TagTargetType
    target_ids: list[str] = Field(min_length=1, max_length=10_000)
    tag: str = Field(min_length=1)


class TagPublic(Tag):
    """A tag with a display name for its source."""

    source_display_name: str = Field(description="The user's name, or the model name")


class TagStats(BaseModel):
    """How one tag is used on one kind of target: analyst labels, model output, and your share."""

    tag: str
    target_type: TagTargetType
    labelled: int = Field(description="Targets an analyst labelled with the tag")
    rejected: int = Field(description="Targets an analyst said are not the tag")
    predicted: int = Field(description="Targets a model tagged or scored")
    by_you: int = Field(description="Of the analyst labels, how many are yours")
    date_last_used: datetime


class TagTrainingReadiness(BaseModel):
    """Whether an image tag has enough analyst labels to train its classifier head."""

    tag: str
    positives: int = Field(description="Images an analyst labelled with the tag")
    negatives: int = Field(description="Images an analyst said are not the tag (hard negatives)")
    min_positives: int = Field(description="Positives a head needs before training includes the tag")
    is_ready: bool
