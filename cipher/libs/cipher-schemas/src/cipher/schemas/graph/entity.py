"""The thin supertype node of the knowledge graph.

An `Entity` is the stable identity that mentions and relationships point at.
Type-specific detail lives in a 1:1 detail row (`organization`, `location`,
`selector`, and the existing `person` table), reached via `entity_id`.
"""

from datetime import date, datetime

from pydantic import Field, SerializationInfo, computed_field, field_serializer, field_validator

from cipher.schemas._base.base import BaseModel, EnumStr, StrEnum, camelize_keys
from cipher.schemas._base.common import PageParams, PaginatedResponse, SortOrder
from cipher.schemas.content.message import TEXT_EMBEDDING_DIMENSION
from cipher.schemas.graph.mention import Mention
from cipher.schemas.graph.ontology import EntitySource, EntityType, RelationshipType, SelectorSubtype, SelectorType

# Types the resolver can mint a provisional entity for (and `dedupe-entities` merges).
NAME_ENTITY_TYPES = frozenset({EntityType.PERSON, EntityType.ORGANIZATION, EntityType.LOCATION})


class EntitySortField(StrEnum):
    DISPLAY_NAME = "display_name"
    DATE_CREATED = "date_created"
    DATE_UPDATED = "date_updated"
    MENTION_COUNT = "mention_count"
    EVIDENCE = "evidence"
    RELEVANCE = "relevance"


class EntityBase(BaseModel):
    """Base entity schema."""

    dataset_id: str | None = Field(
        default=None,
        description="Dataset this entity is locked to; None means it spans datasets (e.g. person bridge nodes)",
    )
    entity_type: EntityType
    display_name: str = Field(max_length=512, description="Primary human-readable label")
    aliases: list[str] = Field(default_factory=list, description="Known alternate surface forms")
    tags: list[str] = Field(default_factory=list, description="Free-form analyst tags")
    notes: str | None = Field(default=None, description="Analyst notes")
    source: EntitySource = Field(default=EntitySource.EXTRACTION, description="How this node was created")
    is_verified: bool = Field(default=False, description="An analyst has confirmed this as a distinct entity")


class EntityCreate(EntityBase):
    """Entity creation schema. The `entity` row id and normalized name are set by the datastore."""

    name_embedding: list[float] | None = Field(
        default=None,
        min_length=TEXT_EMBEDDING_DIMENSION,
        max_length=TEXT_EMBEDDING_DIMENSION,
        description="Embedding of display_name + aliases, for fuzzy resolution",
    )

    @field_validator("display_name")
    @classmethod
    def _collapse_whitespace(cls, value: str) -> str:
        """A name taken from a span that wraps a line ("Dinner Theater", newline, "Restaurant") is one line."""
        return " ".join(value.split())

    @field_validator("aliases")
    @classmethod
    def _collapse_alias_whitespace(cls, value: list[str]) -> list[str]:
        return [" ".join(alias.split()) for alias in value if alias.strip()]


class EntityUpdate(BaseModel):
    """Entity update schema."""

    display_name: str | None = Field(default=None, max_length=512)
    aliases: list[str] | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
    notes: str | None = Field(default=None)
    is_verified: bool | None = Field(default=None)


class EntityBatchRequest(BaseModel):
    """A set of entities to act on at once (bulk verify)."""

    entity_ids: list[str] = Field(min_length=1, max_length=500)


class EntityRetypeRequest(EntityBatchRequest):
    """Auto-created entities to change to another type (person / organization / location)."""

    entity_type: EntityType


class EntityMergeRequest(BaseModel):
    """Auto-created entities to fold into the path entity."""

    source_ids: list[str] = Field(min_length=1, max_length=100)


class UnresolveNameRequest(BaseModel):
    """A resolved name group to send back to the Resolve queue."""

    normalized_value: str


class Entity(EntityBase):
    """Entity model for API responses."""

    id: str
    display_name_normalized: str = Field(description="Case/diacritic-folded display_name for fuzzy match")
    person_id: str | None = Field(default=None, description="Bridge to the legacy person table, if any")
    location_id: str | None = Field(default=None, description="Bridge to the location table, if any")
    selector_type: SelectorType | None = Field(
        default=None, description="Broad selector family; only set for entity_type=selector"
    )
    selector_subtype: SelectorSubtype | None = Field(
        default=None, description="Specific provider/network; only set for entity_type=selector"
    )
    date_created: datetime
    date_updated: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def is_provisional(self) -> bool:
        """Minted by the resolver, not yet merged or promoted (mirrors SQL `is_canonical_entity`)."""
        return (
            self.entity_type in NAME_ENTITY_TYPES
            and self.source != EntitySource.MANUAL
            and not (self.person_id or self.location_id)
        )


class EntitySummary(BaseModel):
    """Lightweight entity reference for graph nodes and related-entity lists."""

    id: str
    entity_type: EntityType
    display_name: str
    is_verified: bool = False

    model_config = {"from_attributes": True}


class EntitySearchParameters(PageParams):
    """Parameters for listing/searching entities."""

    query: str | None = Field(default=None, description="Fuzzy match against display_name/aliases")
    dataset_ids: list[str] | None = Field(default=None, description="Entities in any of these datasets")
    entity_type: EntityType | None = Field(default=None)
    selector_type: SelectorType | None = Field(default=None, description="Only for entity_type=selector")
    selector_subtype: SelectorSubtype | None = Field(
        default=None, description="Only for entity_type=selector (telegram, btc_address, ...)"
    )
    tags: list[str] | None = Field(default=None)
    is_verified: bool | None = Field(default=None)
    provisional: bool | None = Field(
        default=None, description="Auto-created by the resolver and not yet verified or merged (selectors excluded)"
    )
    exclude_source_tags: list[str] | None = Field(
        default=None,
        description="Only entities with a mention in a file carrying none of these source tags (e.g. `promotions`)",
    )
    country: str | None = Field(default=None, description="Detail-row country (organization or location)")
    category: str | None = Field(default=None, description="Organization detail category")
    date_of_birth_from: date | None = Field(default=None, description="Person detail: born on/after")
    date_of_birth_to: date | None = Field(default=None, description="Person detail: born on/before")
    limit: int = Field(default=10, ge=1, le=100)
    sort_by: EntitySortField = Field(default=EntitySortField.DISPLAY_NAME)
    sort_order: SortOrder = Field(default=SortOrder.ASC)


class EntitySearchResult(EntitySummary):
    """An entity returned from a resolution/fuzzy search, with why it matched."""

    is_provisional: bool = Field(default=False, description="Auto-created by the resolver, not yet verified or merged")
    match_reason: str = Field(description="e.g. 'exact selector', 'name trigram', 'name embedding'")
    score: float = Field(ge=0, le=1, description="Blended match confidence")


class MergeSuggestion(BaseModel):
    """An entity an auto-created entity may be a duplicate of -- confirm the match row to merge it in."""

    match_id: str = Field(description="The pending merge `entity_match` row")
    entity_id: str = Field(description="The entity it would merge into")
    entity_name: str
    entity_type: EntityType
    entity_is_provisional: bool
    similarity_score: float
    reasons: list[str] = Field(default_factory=list, description="What agrees, strongest first ('same name', ...)")


class EntityListItem(Entity):
    """An entity row in the dataset table, with the evidence behind it and its open review work."""

    mention_count: int = Field(default=0, description="Mentions resolved to this entity in the dataset")
    file_count: int = Field(default=0, description="Distinct files those mentions are in")
    is_correspondent: bool = Field(default=False, description="Named in an email's from / to / cc header")
    relationship_count: int = Field(default=0, description="Edges touching this entity")
    pending_match_count: int = Field(
        default=0, description="Pending entity_match rows naming this entity (Resolve queue + merge candidates)"
    )
    merge_suggestions: list[MergeSuggestion] = Field(
        default_factory=list, description="Entities it may duplicate, best first (auto-created entities only)"
    )


class PaginatedEntitiesResponse(PaginatedResponse):
    """Paginated response for entities."""

    data: list[EntityListItem] = Field(description="List of entities")


class BreakdownItem(BaseModel):
    """One (label, count) pair for a dataset breakdown chart."""

    key: EnumStr
    count: int


class EntityBreakdown(BaseModel):
    """Counts of a dataset's entities by type / selector type / selector subtype, for the dataset view."""

    total: int
    by_entity_type: list[BreakdownItem]
    by_selector_type: list[BreakdownItem]
    by_selector_subtype: list[BreakdownItem]


class RelatedEntity(BaseModel):
    """One edge in an entity profile: a neighbour plus how it connects."""

    relationship_type: RelationshipType
    direction: str = Field(description="'out' if this entity is the edge source, else 'in'")
    attributes: dict = Field(default_factory=dict, description="Edge attributes, e.g. {'role': 'father'}")
    entity: EntitySummary
    weight: int | None = Field(default=None, description="Edge weight (for emailed, the emails sent that way)")
    mention_count: int | None = Field(
        default=None, description="For selector neighbours: mentions carrying the selector's normalized value"
    )
    selector_type: SelectorType | None = Field(default=None, description="For selector neighbours")
    selector_subtype: SelectorSubtype | None = Field(default=None, description="For selector neighbours")
    normalized_value: str | None = Field(default=None, description="For selector neighbours")


class RelatedEntitySort(StrEnum):
    WEIGHT = "weight"
    RECENT = "recent"
    NAME = "name"


class RelatedEntitySearchParameters(PageParams):
    """Parameters for the paginated neighbours-of-an-entity view."""

    direction: str = Field(default="both", description="'both' | 'out' | 'in'")
    relationship_type: RelationshipType | None = Field(default=None)
    entity_type: EntityType | None = Field(default=None, description="Only neighbours of this type")
    sort: RelatedEntitySort = Field(default=RelatedEntitySort.WEIGHT)
    limit: int = Field(default=25, ge=1, le=200)


class PaginatedRelatedEntitiesResponse(PaginatedResponse):
    """Paginated neighbours of an entity, each with its connecting edge."""

    data: list[RelatedEntity] = Field(description="Neighbouring entities and their edges")


class SelectorMention(BaseModel):
    """A linked selector plus how many mentions carry its normalized value.

    The count spans every dataset and includes still-unresolved mentions, so a
    freshly linked selector immediately shows where its value already appears.
    """

    entity_id: str
    selector_type: SelectorType | None = None
    selector_subtype: SelectorSubtype | None = None
    normalized_value: str | None = None
    mention_count: int = 0
    sent_count: int = Field(default=0, description="Distinct files where this address is a From/Sender header (email)")
    received_count: int = Field(
        default=0, description="Distinct files where this address is a To/Cc/Bcc header (email)"
    )
    text_count: int = Field(default=0, description="Body-text mentions of the value produced by NER")
    pattern_count: int = Field(
        default=0, description="Body-text mentions of the value found by deterministic pattern match"
    )


class EntityProfile(BaseModel):
    """Aggregate dossier for a single entity."""

    entity: Entity
    detail: dict | None = Field(default=None, description="Type-specific detail row, camelCase")
    selectors: list[EntitySummary] = Field(default_factory=list, description="Linked selector entities")
    selector_mentions: list[SelectorMention] = Field(
        default_factory=list, description="Per-selector count of mentions matching its normalized value"
    )
    mention_counts: dict[EnumStr, int] = Field(
        default_factory=dict, description="Count of mentions keyed by MentionProvenance (text / email_header / ...)"
    )
    file_count: int = Field(default=0, description="Distinct files this entity is mentioned in")
    related_entities: list[RelatedEntity] = Field(
        default_factory=list, description="Highest-weight neighbours (preview; full list is paginated)"
    )
    related_total: int = Field(default=0, description="Total non-low-signal edges touching this entity")
    selector_total: int = Field(default=0, description="Total linked selector entities")
    top_mentions: list[Mention] = Field(default_factory=list, description="A few representative mentions")
    face_ids: list[str] = Field(default_factory=list, description="Faces linked via the person bridge")

    @field_serializer("detail")
    def _camel_detail(self, detail: dict | None, info: SerializationInfo) -> dict | None:
        return camelize_keys(detail) if detail is not None and info.by_alias else detail
