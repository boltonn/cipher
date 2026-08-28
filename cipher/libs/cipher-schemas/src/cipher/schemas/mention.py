"""A mention: evidence that some entity has a particular attribute value.

A mention anchors into exactly one piece of evidence -- a character span in
`ExtractedText.content`, a box on an image, or a structured field -- and
asserts `entity.<entity_attribute> = <normalized_value>` (seen as `surface_text`)
for an entity of `entity_type`. Examples: a phone number is a `selector` whose
`value` is the E.164 string; a name in text is a `person` whose `name` is the
folded form; an address is a `location` whose `address` is the cleaned string.

`entity_id` links the mention to a specific entity once it is resolved -- which
may never happen. A facility named only in prose, with no coordinates, stays an
unresolved `location` mention until a geolocation pass or an analyst creates the
entity (see `ontology.ResolutionPolicy`).
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from cipher.schemas.base import BaseModel
from cipher.schemas.common import PaginatedResponse, SortOrder
from cipher.schemas.ontology import EntityType, SelectorKind


class MentionedType(StrEnum):
    """What kind of evidence a mention is anchored in."""

    EXTRACTED_TEXT = "extracted_text"
    IMAGE = "image"
    STRUCTURED_FIELD = "structured_field"


class MentionSortField(StrEnum):
    DATE_CREATED = "date_created"


class MentionBase(BaseModel):
    """Base mention schema."""

    dataset_id: str
    entity_id: str | None = Field(default=None, description="Resolved entity; null while unresolved")
    mentioned_type: MentionedType
    mentioned_id: str = Field(description="id of the extracted_text / image / contact / device row")
    file_id: str | None = Field(default=None, description="Denormalized owning file, when applicable")

    surface_text: str = Field(description="The literal text of the mention span")
    entity_type: EntityType | None = Field(default=None, description="Predicted entity type")
    entity_attribute: str | None = Field(
        default=None,
        description="Which attribute of the entity this asserts, e.g. 'name', 'alias', 'address', 'value'",
    )
    selector_kind: SelectorKind | None = Field(
        default=None, description="Selector `.type` (phone/email/...) when entity_type is selector"
    )
    normalized_value: str | None = Field(
        default=None,
        description="Canonical value of the asserted attribute (E.164 phone, folded name, cleaned address); the resolution blocking key",
    )

    start_offset: int | None = Field(default=None, ge=0, description="Char offset into ExtractedText.content")
    end_offset: int | None = Field(default=None, ge=0, description="Char offset into ExtractedText.content")
    bounding_box: dict | None = Field(default=None, description="Normalized box for image mentions")
    field_path: str | None = Field(default=None, description="Dotted path for structured_field mentions")

    context: str | None = Field(default=None, description="Windowed snippet around the span")
    extractor: str | None = Field(default=None, description="Which extractor produced this (selectors, ner, ...)")
    extraction_model: str | None = Field(default=None, description="Model id/version, if any")
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)


class MentionCreate(MentionBase):
    """Mention creation schema."""

    pass


class MentionUpdate(BaseModel):
    """Partial update for an existing mention (analyst relabel/correction)."""

    entity_id: str | None = Field(default=None, description="Re-point the mention at this entity")
    entity_type: EntityType | None = Field(default=None, description="Corrected predicted type")
    entity_attribute: str | None = Field(default=None, description="Corrected attribute, e.g. name -> alias")
    selector_kind: SelectorKind | None = Field(default=None)
    normalized_value: str | None = Field(default=None)
    surface_text: str | None = Field(default=None)
    context: str | None = Field(default=None)


class MentionResolve(BaseModel):
    """Resolve an unresolved mention: attach to an existing entity or create a new one.

    Exactly one of `entity_id` or `new_entity` must be provided.
    """

    entity_id: str | None = Field(default=None, description="Attach the mention to this entity")
    new_entity: dict | None = Field(
        default=None,
        description="An EntityCreate payload (camelCase); creates the entity then attaches the mention",
    )
    new_entity_detail: dict | None = Field(
        default=None, description="Optional type-specific detail row for the new entity (camelCase)"
    )
    reviewed_by: str = Field(description="User id/name performing the resolution")


class Mention(MentionBase):
    """Mention model for API responses."""

    id: str
    date_created: datetime
    date_updated: datetime

    model_config = {"from_attributes": True}


class MentionSearchParameters(BaseModel):
    """Parameters for listing/searching mentions."""

    entity_id: str | None = Field(default=None)
    file_id: str | None = Field(default=None)
    dataset_id: str | None = Field(default=None)
    mentioned_type: MentionedType | None = Field(default=None)
    entity_type: EntityType | None = Field(default=None)
    entity_attribute: str | None = Field(default=None, description="e.g. 'name', 'address', 'value'")
    resolved: bool | None = Field(default=None, description="True = has entity_id, False = unresolved")
    limit: int = Field(default=25, ge=1, le=200)
    page: int = Field(default=1, ge=1)
    sort_by: MentionSortField = Field(default=MentionSortField.DATE_CREATED)
    sort_order: SortOrder = Field(default=SortOrder.DESC)


class PaginatedMentionsResponse(PaginatedResponse):
    """Paginated response for mentions."""

    data: list[Mention] = Field(description="List of mentions")
