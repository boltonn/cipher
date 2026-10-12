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
from typing import Any

from pydantic import Field, computed_field, model_validator
from pydantic.alias_generators import to_snake

from cipher.schemas._base.base import BaseModel, StrEnum
from cipher.schemas._base.common import PageParams, PaginatedResponse
from cipher.schemas.graph.ontology import EntityType, SelectorSubtype, SelectorType


class MentionedType(StrEnum):
    """What kind of evidence a mention is anchored in."""

    EXTRACTED_TEXT = "extracted_text"
    IMAGE = "image"
    STRUCTURED_FIELD = "structured_field"


MANUAL_EXTRACTOR = "manual"
"""`extractor` of a mention an analyst drew or relabelled -- the gold labels."""


class MentionProvenance(StrEnum):
    """How a mention was found -- its evidence class, coarser than `MentionedType`.

    `MentionedType` says *where* the anchor is (a text span, an image, a field);
    provenance says *what kind of trace* it is, which is what an analyst reasons
    about. An email `To:` line and a name written in prose are both evidence, but
    only the latter is a "mention" in the ordinary sense.
    """

    TEXT = "text"  # a span in body / extracted text (NER, prose)
    EMAIL_HEADER = "email_header"  # a From/To/Cc/Bcc address or display name
    METADATA = "metadata"  # a non-header structured field (vCard, doc properties)
    IMAGE = "image"  # an image region or photo metadata (EXIF)
    PATTERN = "pattern"  # a deterministic pattern match (selectors regex)


def mention_provenance(
    *,
    mentioned_type: MentionedType | str,
    field_path: str | None = None,
    bounding_box: dict | None = None,
    extractor: str | None = None,
) -> MentionProvenance:
    """Classify a mention into its evidence class from the fields it carries.

    First match wins: a header field path beats everything, then image evidence,
    then any other structured field, then a deterministic pattern extractor;
    anything left is a text span.
    """
    if field_path and field_path.startswith("header."):
        return MentionProvenance.EMAIL_HEADER
    if str(mentioned_type) == MentionedType.IMAGE or bounding_box:
        return MentionProvenance.IMAGE
    if str(mentioned_type) == MentionedType.STRUCTURED_FIELD:
        return MentionProvenance.METADATA
    if extractor == "selectors":
        return MentionProvenance.PATTERN
    return MentionProvenance.TEXT


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
    selector_type: SelectorType | None = Field(
        default=None, description="Selector `.type` (phone/email/...) when entity_type is selector"
    )
    selector_subtype: SelectorSubtype | None = Field(
        default=None, description="Specific provider/network/scheme, e.g. telegram, btc_address"
    )
    normalized_value: str | None = Field(
        default=None,
        description="Canonical value of the asserted attribute (E.164 phone, folded name, cleaned address); the resolution blocking key",
    )

    start_offset: int | None = Field(default=None, ge=0, description="Char offset into ExtractedText.content")
    end_offset: int | None = Field(default=None, ge=0, description="Char offset into ExtractedText.content")
    chunk_id: str | None = Field(
        default=None,
        description="The `chunk` whose span contains `start_offset` -- the materialized "
        "chunk<->mention join, set at extraction time. Null for header/metadata mentions and "
        "until backfilled.",
    )
    bounding_box: dict | None = Field(default=None, description="Normalized box for image mentions")
    field_path: str | None = Field(default=None, description="Dotted path for structured_field mentions")

    context: str | None = Field(default=None, description="Windowed snippet around the span")
    extractor: str | None = Field(default=None, description="Which extractor produced this (selectors, ner, ...)")
    extraction_model: str | None = Field(default=None, description="Model id/version, if any")
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)


class MentionCreate(MentionBase):
    """Mention creation schema."""

    @model_validator(mode="before")
    @classmethod
    def _trim_whitespace(cls, data: Any) -> Any:
        """Drop edge whitespace from the span (shifting its offsets to match) and collapse it in the value."""
        if not isinstance(data, dict):
            return data
        data = {to_snake(key): value for key, value in data.items()}
        surface, start, end = data.get("surface_text"), data.get("start_offset"), data.get("end_offset")
        if isinstance(surface, str):
            trimmed = surface.strip()
            if start is not None and end is not None and end - start == len(surface):
                data["start_offset"] = start + len(surface) - len(surface.lstrip())
                data["end_offset"] = data["start_offset"] + len(trimmed)
            data["surface_text"] = trimmed
        if isinstance(value := data.get("normalized_value"), str):
            data["normalized_value"] = " ".join(value.split())
        return data


class MentionUpdate(BaseModel):
    """Partial update for an existing mention (analyst relabel/correction)."""

    entity_id: str | None = Field(default=None, description="Re-point the mention at this entity")
    entity_type: EntityType | None = Field(default=None, description="Corrected predicted type")
    entity_attribute: str | None = Field(default=None, description="Corrected attribute, e.g. name -> alias")
    selector_type: SelectorType | None = Field(default=None)
    selector_subtype: SelectorSubtype | None = Field(default=None)
    normalized_value: str | None = Field(default=None, description="Recomputed from `surface_text` when omitted")
    surface_text: str | None = Field(default=None)
    start_offset: int | None = Field(default=None, ge=0, description="Moved span start (send with `end_offset`)")
    end_offset: int | None = Field(default=None, ge=0, description="Moved span end")
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
    reviewed_by: str | None = Field(
        default=None, description="Set server-side from the signed-in user; ignored from clients"
    )


class Mention(MentionBase):
    """Mention model for API responses."""

    id: str
    date_created: datetime
    date_updated: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def provenance(self) -> MentionProvenance:
        """Evidence class, derived so the UI can group and filter without a join."""
        return mention_provenance(
            mentioned_type=self.mentioned_type,
            field_path=self.field_path,
            bounding_box=self.bounding_box,
            extractor=self.extractor,
        )


class MentionSearchParameters(PageParams):
    """Parameters for listing/searching mentions."""

    entity_id: str | None = Field(default=None)
    file_id: str | None = Field(default=None)
    dataset_id: str | None = Field(default=None)
    dataset_ids: list[str] | None = Field(
        default=None, description="Restrict to any of these datasets (set server-side to the caller's access)"
    )
    mentioned_type: MentionedType | None = Field(default=None)
    provenance: MentionProvenance | None = Field(
        default=None, description="Filter by evidence class (text / email_header / metadata / image / pattern)"
    )
    entity_type: EntityType | None = Field(default=None)
    entity_attribute: str | None = Field(default=None, description="e.g. 'name', 'address', 'value'")
    selector_type: SelectorType | None = Field(default=None, description="Filter selector mentions by type")
    selector_subtype: SelectorSubtype | None = Field(
        default=None, description="Filter selector mentions by subtype (telegram, btc_address, ...)"
    )
    normalized_value: str | None = Field(
        default=None, description="Exact match on the resolution blocking key (E.164 phone, folded name, ...)"
    )
    resolved: bool | None = Field(default=None, description="True = has entity_id, False = unresolved")
    # A per-file mention list (extracted-text view) asks for every span at once,
    # which can run into the hundreds -- hence a higher cap than the usual 200.
    limit: int = Field(default=25, ge=1, le=500)
    sort_by: MentionSortField = Field(default=MentionSortField.DATE_CREATED)


class PaginatedMentionsResponse(PaginatedResponse):
    """Paginated response for mentions."""

    data: list[Mention] = Field(description="List of mentions")


class UnresolvedNameGroup(BaseModel):
    """One distinct unresolved `name` value in one dataset's review queue, with its footprint."""

    dataset_id: str = Field(description="Dataset the name group belongs to (resolution runs per dataset)")
    normalized_value: str = Field(description="Folded name -- the resolution blocking key")
    surface: str = Field(description="Most common surface form seen for this name")
    mention_count: int = Field(description="Unresolved name mentions sharing this value")
    file_count: int = Field(description="Distinct files those mentions appear in")
    is_correspondent: bool = Field(default=False, description="Named in an email's from / to / cc header")
    sample_context: str | None = Field(default=None, description="One context snippet, for display")
    sample_surface: str | None = Field(default=None, description="The name as written in `sample_context`")
    suggested_type: EntityType | None = Field(
        default=None, description="Heuristic person/organization guess; null = undecided"
    )


class PaginatedUnresolvedNamesResponse(PaginatedResponse):
    """Paginated distinct-name view of the review queue."""

    data: list[UnresolvedNameGroup] = Field(description="Name groups, noisiest first")


class ResolveNameGroupRequest(BaseModel):
    """Resolve every unresolved `name` mention of one value at once."""

    dataset_id: str
    normalized_value: str
    entity_type: EntityType = Field(default=EntityType.PERSON, description="Kind of entity to attach to / create")
    entity_id: str | None = Field(default=None, description="Attach to this existing entity")
    display_name: str | None = Field(
        default=None, description="Display name for a new entity (defaults to the surface form)"
    )
    reviewed_by: str | None = Field(default=None)


class ResolveNameGroupResult(BaseModel):
    """Outcome of resolving a name group."""

    entity_id: str
    mentions_attached: int
    has_selector_edges: int = Field(description="has_selector edges present after linking")


class DismissNameGroupRequest(BaseModel):
    """Discard every unresolved `name` mention of one value (not a real entity)."""

    dataset_id: str
    normalized_value: str


class NameGroupKey(BaseModel):
    """One name group: a dataset's unresolved `name` mentions of one value."""

    dataset_id: str
    normalized_value: str
    display_name: str | None = Field(default=None, description="Display name if a new entity is created for it")


class ResolveNameGroupsRequest(BaseModel):
    """Resolve several name groups in one decision: each to a new entity of its own, or all to one entity."""

    groups: list[NameGroupKey] = Field(min_length=1, max_length=200)
    entity_type: EntityType = Field(default=EntityType.PERSON, description="Kind of entity to attach to / create")
    entity_id: str | None = Field(default=None, description="Attach every group to this existing entity")


class ResolveNameGroupsResult(BaseModel):
    """Outcome of resolving several name groups."""

    entity_ids: list[str] = Field(description="The entity each group was resolved to, in request order")
    mentions_attached: int


class DismissNameGroupsRequest(BaseModel):
    """Discard several name groups (not real entities)."""

    groups: list[NameGroupKey] = Field(min_length=1, max_length=200)


class ResolvedName(BaseModel):
    """One name the evidence uses for an entity (a resolved name group), and whether it's a curated alias.

    Resolving a name group points its mentions at the entity; it does not make the name an
    alias. Misspellings, punctuation variants, a bare surname or "friend" all resolve here,
    but only the names an analyst adds become aliases.
    """

    normalized_value: str
    surface: str = Field(description="Most common way the name is written")
    mention_count: int
    is_alias: bool = False
