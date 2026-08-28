"""The thin supertype node of the knowledge graph.

An `Entity` is the stable identity that mentions and relationships point at.
Type-specific detail lives in a 1:1 detail row (`organization`, `location`,
`selector`, and the existing `person` table), reached via `entity_id`.
"""

from datetime import date, datetime
from enum import StrEnum

from pydantic import Field

from cipher.schemas.base import BaseModel
from cipher.schemas.common import PaginatedResponse, SortOrder
from cipher.schemas.mention import Mention
from cipher.schemas.message import TEXT_EMBEDDING_DIMENSION
from cipher.schemas.ontology import EntitySource, EntityType, RelationshipType, SelectorKind


class EntitySortField(StrEnum):
    DISPLAY_NAME = "display_name"
    DATE_CREATED = "date_created"
    DATE_UPDATED = "date_updated"


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


class EntityUpdate(BaseModel):
    """Entity update schema."""

    display_name: str | None = Field(default=None, max_length=512)
    aliases: list[str] | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
    notes: str | None = Field(default=None)
    is_verified: bool | None = Field(default=None)


class Entity(EntityBase):
    """Entity model for API responses."""

    id: str
    display_name_normalized: str = Field(description="Case/diacritic-folded display_name for fuzzy match")
    person_id: str | None = Field(default=None, description="Bridge to the legacy person table, if any")
    date_created: datetime
    date_updated: datetime

    model_config = {"from_attributes": True}


class EntitySummary(BaseModel):
    """Lightweight entity reference for graph nodes and related-entity lists."""

    id: str
    entity_type: EntityType
    display_name: str
    is_verified: bool = False

    model_config = {"from_attributes": True}


class EntitySearchParameters(BaseModel):
    """Parameters for listing/searching entities."""

    query: str | None = Field(default=None, description="Fuzzy match against display_name/aliases")
    dataset_id: str | None = Field(default=None)
    entity_type: EntityType | None = Field(default=None)
    selector_kind: SelectorKind | None = Field(default=None, description="Only for entity_type=selector")
    tags: list[str] | None = Field(default=None)
    is_verified: bool | None = Field(default=None)
    country: str | None = Field(default=None, description="Detail-row country (organization or location)")
    org_type: str | None = Field(default=None, description="Organization detail org_type")
    date_of_birth_from: date | None = Field(default=None, description="Person detail: born on/after")
    date_of_birth_to: date | None = Field(default=None, description="Person detail: born on/before")
    limit: int = Field(default=10, ge=1, le=100)
    page: int = Field(default=1, ge=1)
    sort_by: EntitySortField = Field(default=EntitySortField.DATE_UPDATED)
    sort_order: SortOrder = Field(default=SortOrder.DESC)


class EntitySearchResult(EntitySummary):
    """An entity returned from a resolution/fuzzy search, with why it matched."""

    match_reason: str = Field(description="e.g. 'exact selector', 'name trigram', 'name embedding'")
    score: float = Field(ge=0, le=1, description="Blended match confidence")


class PaginatedEntitiesResponse(PaginatedResponse):
    """Paginated response for entities."""

    data: list[Entity] = Field(description="List of entities")


class RelatedEntity(BaseModel):
    """One edge in an entity profile: a neighbour plus how it connects."""

    relationship_type: RelationshipType
    direction: str = Field(description="'out' if this entity is the edge source, else 'in'")
    entity: EntitySummary


class EntityProfile(BaseModel):
    """Aggregate dossier for a single entity."""

    entity: Entity
    detail: dict | None = Field(default=None, description="Type-specific detail row, camelCase")
    selectors: list[EntitySummary] = Field(default_factory=list, description="Linked selector entities")
    mention_counts: dict[str, int] = Field(
        default_factory=dict, description="Count of mentions keyed by mentioned_type"
    )
    related_entities: list[RelatedEntity] = Field(default_factory=list)
    top_mentions: list[Mention] = Field(default_factory=list, description="A few representative mentions")
    face_ids: list[str] = Field(default_factory=list, description="Faces linked via the person bridge")
