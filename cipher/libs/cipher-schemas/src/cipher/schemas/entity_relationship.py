"""Typed edges between entity nodes: confirmed relationships and review candidates.

Mirrors the face/face_match split -- `EntityRelationship` is an asserted edge,
`RelationshipCandidate` is a proposed edge awaiting analyst review.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from cipher.schemas.base import BaseModel
from cipher.schemas.common import PaginatedResponse, SortOrder
from cipher.schemas.entity import EntitySummary
from cipher.schemas.ontology import RelationshipSource, RelationshipType


class TraversalDirection(StrEnum):
    """Which edge directions to follow from a starting node."""

    OUT = "out"
    IN = "in"
    BOTH = "both"


class RelationshipCandidateStatus(StrEnum):
    """Review state of a proposed edge."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class RelationshipCandidateMethod(StrEnum):
    """How a proposed edge was generated."""

    CO_MENTION = "co_mention"
    LLM = "llm"
    SELECTOR_INFERENCE = "selector_inference"
    MANUAL = "manual"


class EntityRelationshipBase(BaseModel):
    """Base confirmed-edge schema."""

    dataset_id: str
    src_entity_id: str
    dst_entity_id: str
    relationship_type: RelationshipType
    directed: bool = Field(default=True)
    weight: float | None = Field(default=None, description="Optional strength/frequency of the edge")
    source: RelationshipSource = Field(default=RelationshipSource.EXTRACTION)
    attributes: dict = Field(default_factory=dict, description="Edge-specific data, e.g. role title")
    date_observed_start: datetime | None = Field(default=None)
    date_observed_end: datetime | None = Field(default=None)


class EntityRelationshipCreate(EntityRelationshipBase):
    """Confirmed-edge creation schema."""

    pass


class EntityRelationship(EntityRelationshipBase):
    """Confirmed-edge model for API responses."""

    id: str
    date_created: datetime
    date_updated: datetime

    model_config = {"from_attributes": True}


class RelationshipCandidateBase(BaseModel):
    """Base proposed-edge schema."""

    dataset_id: str
    src_entity_id: str
    dst_entity_id: str
    relationship_type: RelationshipType
    confidence: float = Field(ge=0, le=1)
    method: RelationshipCandidateMethod = RelationshipCandidateMethod.CO_MENTION
    evidence_mention_id: str | None = Field(default=None, description="A mention supporting this edge")


class RelationshipCandidateCreate(RelationshipCandidateBase):
    """Proposed-edge creation schema."""

    pass


class RelationshipCandidate(RelationshipCandidateBase):
    """Proposed-edge model for API responses."""

    id: str
    status: RelationshipCandidateStatus = RelationshipCandidateStatus.PENDING
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    date_created: datetime

    model_config = {"from_attributes": True}


class RelationshipReview(BaseModel):
    """Schema for an analyst resolving a proposed edge."""

    status: RelationshipCandidateStatus = Field(description="Must be 'confirmed' or 'rejected'")
    reviewed_by: str
    review_note: str | None = None


class RelationshipSearchParameters(BaseModel):
    """Parameters for listing an entity's confirmed edges."""

    entity_id: str | None = Field(default=None, description="Edges touching this entity (either endpoint)")
    dataset_id: str | None = Field(default=None)
    relationship_type: RelationshipType | None = Field(default=None)
    direction: TraversalDirection = Field(default=TraversalDirection.BOTH)
    limit: int = Field(default=50, ge=1, le=500)
    page: int = Field(default=1, ge=1)


class RelationshipCandidateSearchParameters(BaseModel):
    """Parameters for the relationship review queue."""

    src_entity_id: str | None = Field(default=None)
    dst_entity_id: str | None = Field(default=None)
    dataset_id: str | None = Field(default=None)
    status: RelationshipCandidateStatus | None = Field(default=RelationshipCandidateStatus.PENDING)
    limit: int = Field(default=25, ge=1, le=100)
    page: int = Field(default=1, ge=1)
    sort_order: SortOrder = Field(default=SortOrder.DESC)


class PaginatedRelationshipsResponse(PaginatedResponse):
    """Paginated response for confirmed edges."""

    data: list[EntityRelationship] = Field(description="List of relationships")


class PaginatedRelationshipCandidatesResponse(PaginatedResponse):
    """Paginated response for proposed edges."""

    data: list[RelationshipCandidate] = Field(description="List of relationship candidates")


class GraphResponse(BaseModel):
    """Result of a bounded graph traversal."""

    nodes: list[EntitySummary] = Field(default_factory=list)
    edges: list[EntityRelationship] = Field(default_factory=list)
