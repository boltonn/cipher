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
from cipher.schemas.graph.entity_resolution import ResolutionExplanation
from cipher.schemas.graph.mention import UnresolvedNameGroup

# Back-compat aliases -- prefer the shared names from `cipher.schemas._base.review`.
EntityMatchStatus = ReviewStatus
EntityMatchSortField = MatchSortField


class EntityMatchMethod(StrEnum):
    """How a candidate resolution was proposed -- the dominant blocking/scoring signal.

    Stored as varchar (`native_enum=False`); the column is sized to the longest
    member name (`selector_blocking`, 16), so every value here fits without a
    widening migration.
    """

    SELECTOR_BLOCKING = "selector_blocking"
    NAME_EXACT = "name_exact"
    NAME_TRANSLIT = "name_translit"
    NAME_PHONETIC = "name_phonetic"
    NAME_STRUCTURE = "name_structure"
    NAME_FUZZY = "name_fuzzy"
    NAME_EMBEDDING = "name_embedding"
    LLM = "llm"
    SPLINK = "splink"
    MANUAL = "manual"
    ASSISTANT = "assistant"  # proposed from chat; still needs an analyst decision


class DecisionSource(StrEnum):
    """Who/what set a match's status -- so calibration can weight the label.

    Stored as varchar; `sibling_auto` is the longest (12).
    """

    ANALYST = "analyst"  # an analyst explicitly confirmed / rejected in the queue
    SIBLING_AUTO = "sibling_auto"  # rejected because a sibling candidate for the same name group was confirmed
    RECONCILE = "reconcile"  # closed by the sweep because the name group is fully resolved
    SYSTEM_AUTO = "system_auto"  # the sweep's one always-auto rule (exact selector on a structured field)


class EntityMatchBase(BaseModel):
    """Base entity match schema."""

    dataset_id: str
    entity_id: str = Field(description="The canonical entity this resolves to")
    mention_id: str | None = Field(default=None, description="The unresolved mention, if resolving a single mention")
    normalized_value: str | None = Field(
        default=None,
        description="Name-group key: when set (and mention_id is null), confirming resolves every "
        "unresolved `name` mention of this value",
    )
    mention_count: int | None = Field(default=None, description="Mentions the group-level row covers")
    provisional_entity_id: str | None = Field(
        default=None, description="A provisionally-created entity to merge into the canonical one"
    )
    similarity_score: float = Field(ge=0, le=1)
    match_method: EntityMatchMethod = EntityMatchMethod.SELECTOR_BLOCKING
    decision_source: DecisionSource | None = Field(
        default=None, description="How this row's status was set (null while pending)"
    )
    explanation: ResolutionExplanation | None = Field(
        default=None, description="Per-feature score breakdown; rendered as the review-queue 'why'"
    )


class EntityMatchCreate(EntityMatchBase):
    """Entity match creation schema."""

    pass


class EntityMatchReview(ReviewDecision):
    """Schema for an analyst resolving a candidate."""

    pass


class EntityMatchBatchItem(BaseModel):
    """One decision in a bulk review submission."""

    match_id: str
    status: ReviewStatus = Field(description="'confirmed' or 'rejected'")
    review_note: str | None = None


class EntityMatchBatchReview(BaseModel):
    """Resolve many candidates in one call -- the fast bulk-annotation path."""

    reviewed_by: str | None = Field(
        default=None, description="Set server-side from the signed-in user; ignored from clients"
    )
    decisions: list[EntityMatchBatchItem] = Field(min_length=1, max_length=500)


class NameGroupDismissRequest(BaseModel):
    """'None of these candidates is right' -- reject every pending row for a name group."""

    dataset_id: str
    normalized_value: str
    reviewed_by: str | None = Field(
        default=None, description="Set server-side from the signed-in user; ignored from clients"
    )
    review_note: str | None = None


class EntityMatch(ReviewableMixin, EntityMatchBase):
    """Entity match model for API responses."""

    id: str
    date_created: datetime
    entity_name: str | None = Field(default=None, description="Display name of `entity_id` (read-time only)")
    entity_type: str | None = Field(default=None, description="Type of `entity_id` (read-time only)")
    entity_person_id: str | None = Field(
        default=None, description="`person_id` of `entity_id` if it bridges a person record (read-time only)"
    )
    provisional_name: str | None = Field(
        default=None, description="Display name of `provisional_entity_id` on a merge proposal (read-time only)"
    )
    entity_is_provisional: bool | None = Field(
        default=None, description="`entity_id` is a provisional entity, not a canonical one (read-time only)"
    )
    entity_pending_merge_count: int | None = Field(
        default=None, description="Pending merge proposals filed against a provisional `entity_id` (read-time only)"
    )

    model_config = {"from_attributes": True}


class EntityMatchGroup(BaseModel):
    """One name group in the grouped review queue: the top candidate + its alternatives."""

    dataset_id: str
    normalized_value: str
    surface: str = Field(description="Most common surface form of the name")
    mention_count: int
    file_count: int = 0
    status: ReviewStatus
    top: EntityMatch
    alternatives: list[EntityMatch] = Field(default_factory=list)


class PaginatedEntityMatchGroupsResponse(PaginatedResponse):
    """Grouped review queue -- one card per name, alternatives nested."""

    data: list[EntityMatchGroup] = Field(description="Name groups awaiting review")
    hidden_provisional_total: int = Field(
        default=0,
        description="Name groups left out because their only candidates are provisional (auto-created) entities",
    )


class EntityMergeGroup(BaseModel):
    """One provisional entity in the merge-review queue.

    The resolver-minted stub plus the canonical entities it may be a duplicate of.
    """

    dataset_id: str
    provisional_entity_id: str
    provisional_name: str
    provisional_entity_type: str
    mention_count: int = 0
    status: ReviewStatus
    candidates: list[EntityMatch] = Field(default_factory=list, description="Canonical merge targets, best first")


class PaginatedEntityMergeGroupsResponse(PaginatedResponse):
    """Merge-review queue -- one card per provisional entity."""

    data: list[EntityMergeGroup] = Field(description="Provisional entities awaiting a merge decision")


class EntityMergeSearchParameters(PageParams):
    """Parameters for the entity-merge review queue."""

    dataset_id: str | None = None
    status: ReviewStatus | None = Field(default=ReviewStatus.PENDING)
    limit: int = Field(default=25, ge=1, le=100)
    sort_by: MatchSortField = Field(default=MatchSortField.SIMILARITY_SCORE)


class EntityMatchSearchParameters(PageParams):
    """Parameters for the entity resolution review queue."""

    entity_id: str | None = None
    mention_id: str | None = None
    dataset_id: str | None = None
    status: ReviewStatus | None = Field(default=ReviewStatus.PENDING)
    min_similarity: float | None = Field(default=None, ge=0, le=1)
    include_provisional_entities: bool = Field(
        default=True, description="Also list candidates that are provisional entities (grouped queue only)"
    )
    limit: int = Field(default=10, ge=1, le=100)
    sort_by: MatchSortField = Field(default=MatchSortField.SIMILARITY_SCORE)


class PaginatedEntityMatchesResponse(PaginatedResponse):
    """Paginated response for entity matches."""

    data: list[EntityMatch] = Field(description="List of entity matches")


class NameGroupInQueue(UnresolvedNameGroup):
    """One name group in the Resolve queue: the unresolved name plus its pending resolutions."""

    resolutions: list[EntityMatch] = Field(
        default_factory=list,
        description="Pending resolutions proposing this name group is an existing entity, best first",
    )


class PaginatedResolveQueueResponse(PaginatedResponse):
    """Paginated Resolve queue -- one row per unresolved name group."""

    data: list[NameGroupInQueue] = Field(description="Name groups, most mentions first")
