"""Candidate resolution of a mention (or provisional entity) to a canonical entity.

The text-world analogue of `FaceMatch`: entity resolution proposes that an
unresolved mention -- or a provisionally-created entity -- is the same as an
existing canonical entity, and an analyst confirms or rejects it.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from cipher.schemas.base import BaseModel
from cipher.schemas.common import PaginatedResponse, SortOrder


class EntityMatchStatus(StrEnum):
    """Review state of a candidate resolution."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class EntityMatchMethod(StrEnum):
    """How a candidate resolution was proposed."""

    SELECTOR_BLOCKING = "selector_blocking"
    NAME_FUZZY = "name_fuzzy"
    NAME_EMBEDDING = "name_embedding"
    LLM = "llm"
    MANUAL = "manual"


class EntityMatchSortField(StrEnum):
    DATE_CREATED = "date_created"
    SIMILARITY_SCORE = "similarity_score"


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


class EntityMatchReview(BaseModel):
    """Schema for an analyst resolving a candidate."""

    status: EntityMatchStatus = Field(description="Must be 'confirmed' or 'rejected'")
    reviewed_by: str
    review_note: str | None = None


class EntityMatch(EntityMatchBase):
    """Entity match model for API responses."""

    id: str
    status: EntityMatchStatus = EntityMatchStatus.PENDING
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    date_created: datetime

    model_config = {"from_attributes": True}


class EntityMatchSearchParameters(BaseModel):
    """Parameters for the entity resolution review queue."""

    entity_id: str | None = None
    mention_id: str | None = None
    dataset_id: str | None = None
    status: EntityMatchStatus | None = Field(default=EntityMatchStatus.PENDING)
    min_similarity: float | None = Field(default=None, ge=0, le=1)
    limit: int = Field(default=10, ge=1, le=100)
    page: int = Field(default=1, ge=1)
    sort_by: EntityMatchSortField = Field(default=EntityMatchSortField.SIMILARITY_SCORE)
    sort_order: SortOrder = Field(default=SortOrder.DESC)


class PaginatedEntityMatchesResponse(PaginatedResponse):
    """Paginated response for entity matches."""

    data: list[EntityMatch] = Field(description="List of entity matches")
