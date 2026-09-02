"""Candidate resolution of a mention (or provisional entity) to a canonical entity.

The text-world analogue of `FaceMatch`: entity resolution proposes that an
unresolved mention -- or a provisionally-created entity -- is the same as an
existing canonical entity, and an analyst confirms or rejects it. The review
vocabulary (status, decision body, review-state fields, sort axis) is shared
with `face_match` and `entity_relationship` via `cipher.schemas._base.review`.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import PageParams, PaginatedResponse
from cipher.schemas._base.review import MatchSortField, ReviewableMixin, ReviewDecision, ReviewStatus

# Back-compat aliases -- prefer the shared names from `cipher.schemas._base.review`.
EntityMatchStatus = ReviewStatus
EntityMatchSortField = MatchSortField


class EntityMatchMethod(StrEnum):
    """How a candidate resolution was proposed."""

    SELECTOR_BLOCKING = "selector_blocking"
    NAME_FUZZY = "name_fuzzy"
    NAME_EMBEDDING = "name_embedding"
    LLM = "llm"
    MANUAL = "manual"


class EntityMatchBase(BaseModel):
    """Base entity match schema."""

    dataset_id: str
    entity_id: str = Field(description="The canonical entity this resolves to")
    mention_id: str | None = Field(default=None, description="The unresolved mention, if resolving a mention")
    provisional_entity_id: str | None = Field(
        default=None, description="A provisionally-created entity to merge into the canonical one"
    )
    similarity_score: float = Field(ge=0, le=1)
    match_method: EntityMatchMethod = EntityMatchMethod.SELECTOR_BLOCKING


class EntityMatchCreate(EntityMatchBase):
    """Entity match creation schema."""

    pass


class EntityMatchReview(ReviewDecision):
    """Schema for an analyst resolving a candidate."""

    pass


class EntityMatch(ReviewableMixin, EntityMatchBase):
    """Entity match model for API responses."""

    id: str
    date_created: datetime

    model_config = {"from_attributes": True}


class EntityMatchSearchParameters(PageParams):
    """Parameters for the entity resolution review queue."""

    entity_id: str | None = None
    mention_id: str | None = None
    dataset_id: str | None = None
    status: ReviewStatus | None = Field(default=ReviewStatus.PENDING)
    min_similarity: float | None = Field(default=None, ge=0, le=1)
    limit: int = Field(default=10, ge=1, le=100)
    sort_by: MatchSortField = Field(default=MatchSortField.SIMILARITY_SCORE)


class PaginatedEntityMatchesResponse(PaginatedResponse):
    """Paginated response for entity matches."""

    data: list[EntityMatch] = Field(description="List of entity matches")
