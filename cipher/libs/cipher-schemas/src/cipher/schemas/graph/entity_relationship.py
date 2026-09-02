"""Typed edges between entity nodes: confirmed relationships and review candidates.

Mirrors the face/face_match split -- `EntityRelationship` is an asserted edge,
`RelationshipCandidate` is a proposed edge awaiting analyst review.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import PageParams, PaginatedResponse
from cipher.schemas._base.review import ReviewableMixin, ReviewDecision, ReviewStatus
from cipher.schemas.graph.entity import EntitySummary
from cipher.schemas.graph.ontology import RelationshipSource, RelationshipType

# Back-compat alias -- prefer `ReviewStatus` from `cipher.schemas._base.review`.
RelationshipCandidateStatus = ReviewStatus


class TraversalDirection(StrEnum):
    """Which edge directions to follow from a starting node."""

    OUT = "out"
    IN = "in"
    BOTH = "both"


class RelationshipCandidateMethod(StrEnum):
    """How a proposed edge was generated."""

    CO_MENTION = "co_mention"
    LLM = "llm"
    SELECTOR_INFERENCE = "selector_inference"
    MANUAL = "manual"


class EntityRelationshipBase(BaseModel):
    """Base confirmed-edge schema."""

    dataset_id: str | None = Field(
        default=None,
        description="Dataset the edge belongs to; None when it spans datasets (e.g. two person bridge nodes)",
    )
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


class RelationshipCandidate(ReviewableMixin, RelationshipCandidateBase):
    """Proposed-edge model for API responses."""

    id: str
    date_created: datetime

    model_config = {"from_attributes": True}


class RelationshipReview(ReviewDecision):
    """Schema for an analyst resolving a proposed edge."""

    pass


class RelationshipSearchParameters(PageParams):
    """Parameters for listing an entity's confirmed edges."""

    entity_id: str | None = Field(default=None, description="Edges touching this entity (either endpoint)")
    dataset_id: str | None = Field(default=None)
    relationship_type: RelationshipType | None = Field(default=None)
    direction: TraversalDirection = Field(default=TraversalDirection.BOTH)
    limit: int = Field(default=50, ge=1, le=500)


class RelationshipCandidateSearchParameters(PageParams):
    """Parameters for the relationship review queue."""

    src_entity_id: str | None = Field(default=None)
    dst_entity_id: str | None = Field(default=None)
    dataset_id: str | None = Field(default=None)
    status: ReviewStatus | None = Field(default=ReviewStatus.PENDING)
    limit: int = Field(default=25, ge=1, le=100)


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
