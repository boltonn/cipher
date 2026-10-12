"""Wire schemas for the pyprompt service.

Two layers:

* **``Llm*``** models are the *exact* shape the model is asked to return
  (`response_format`). They are deliberately offset-free -- an LLM cannot count
  characters -- and use plain strings for dates and roles.
* The **public** results (`EntityExtraction`, `EventExtraction`) are what the
  runner returns after resolving character offsets (`offsets.locate`) and
  coercing roles/dates. `EntitySpan` / `RelationSpan` are the shared
  analytics -> orchestration contract from `cipher.schemas.graph.spans`, so
  pyprompt is a drop-in third `--extractor` next to `pygliner` / `nerd`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, create_model

from cipher.schemas.graph.event import DatePrecision, EventDetails, EventStatus, EventType
from cipher.schemas.graph.ontology import default_ner_labels, default_relation_labels
from cipher.schemas.graph.spans import EntitySpan, RelationSpan

__all__ = [
    "EntitySpan",
    "RelationSpan",
    "LlmEntity",
    "LlmRelation",
    "LlmEntityOutput",
    "build_entity_output_model",
    "build_combined_output_model",
    "LlmEventParticipant",
    "LlmEventPlace",
    "LlmEvent",
    "LlmEventOutput",
    "LlmCombinedOutput",
    "EntityExtraction",
    "ParsedEvent",
    "EventExtraction",
    "CombinedExtraction",
    "EntityRequest",
    "EventRequest",
    "ExtractRequest",
    "RunRequest",
]


# --------------------------------------------------------------------------- #
# What the model returns (response_format)                                    #
# --------------------------------------------------------------------------- #
class LlmEntity(BaseModel):
    """One entity mention as emitted by the model."""

    surface_text: str = Field(description="The entity exactly as it appears in the text")
    label: str = Field(description="One of the provided labels")


class LlmRelation(BaseModel):
    """One directed relation between two entity surface forms."""

    head_text: str = Field(description="Surface form of the source entity")
    tail_text: str = Field(description="Surface form of the target entity")
    label: str = Field(description="One of the provided relation labels")


class LlmEntityOutput(BaseModel):
    """Full structured payload for the entities/relations prompt.

    `LlmEntity`/`LlmRelation` here keep `label: str` for typing convenience;
    `build_entity_output_model()` produces the *constrained* variant actually
    sent as `response_format`, where `label` is a `Literal` of the exact
    ontology vocabulary so the model cannot emit an out-of-schema label.
    """

    entities: list[LlmEntity] = Field(default_factory=list)
    relations: list[LlmRelation] = Field(default_factory=list)


@lru_cache(maxsize=32)
def build_entity_output_model(labels: tuple[str, ...], relation_labels: tuple[str, ...]) -> type[BaseModel]:
    """A `response_format` model whose `label` fields are enum-locked to the given vocabulary.

    OpenAI structured output turns each `Literal` into a JSON-schema `enum`, so an
    unknown or paraphrased label is impossible rather than caught downstream.
    Cached per distinct label set (the default ontology vocabulary in practice).
    """
    entity_label = Literal[labels]  # type: ignore
    relation_label = Literal[relation_labels]  # type: ignore

    entity_model = create_model(
        "LlmEntityStrict",
        surface_text=(str, Field(description="The entity exactly as it appears in the text")),
        label=(entity_label, Field(description="Exactly one of the provided entity labels")),
    )
    relation_model = create_model(
        "LlmRelationStrict",
        head_text=(str, Field(description="Surface form of the source entity")),
        tail_text=(str, Field(description="Surface form of the target entity")),
        label=(relation_label, Field(description="Exactly one of the provided relation labels")),
    )
    return create_model(
        "LlmEntityOutputStrict",
        entities=(list[entity_model], Field(default_factory=list)),  # type: ignore
        relations=(list[relation_model], Field(default_factory=list)),  # type: ignore
    )


class LlmEventParticipant(BaseModel):
    """A person or organization tied to an event, by surface name."""

    name: str
    role: str = Field(description="traveler | attendee | organizer | host | guest")


class LlmEventPlace(BaseModel):
    """A place tied to an event, by surface text."""

    text: str
    role: str = Field(description="venue | origin | destination")


class LlmEvent(BaseModel):
    """One dated occurrence as emitted by the model."""

    title: str
    summary: str | None = None
    event_type: str = Field(description="travel | lodging | reservation | meeting | gathering | delivery | other")
    date_start: str | None = Field(default=None, description="ISO 8601; date or datetime")
    date_end: str | None = Field(default=None, description="ISO 8601; date or datetime")
    timezone: str | None = Field(default=None, description="IANA tz name if stated")
    is_all_day: bool = False
    date_precision: str = Field(default="day", description="exact | day | month | year | approximate")
    status: str = Field(default="confirmed", description="confirmed | tentative | cancelled | completed")
    confidence: float | None = Field(default=None, description="0-1: your certainty this is a real dated event")
    participants: list[LlmEventParticipant] = Field(default_factory=list)
    places: list[LlmEventPlace] = Field(default_factory=list)

    # Type-specific facts -- fill only the ones that apply to `event_type` and are
    # stated in the passage (see the prompt). Flat here; mapped to the typed
    # `details` union by the runner.
    operator: str | None = Field(default=None, description="Carrier / hotel / restaurant / provider")
    number: str | None = Field(default=None, description="Flight or train number (travel)")
    confirmation: str | None = Field(default=None, description="Confirmation code / record locator")
    nights: int | None = Field(default=None, description="Nights booked (lodging)")
    guests: int | None = Field(default=None, description="Guest count (lodging)")
    party_size: int | None = Field(default=None, description="Party size (reservation)")
    carrier: str | None = Field(default=None, description="Shipping carrier (delivery)")
    tracking_number: str | None = Field(default=None, description="Tracking number (delivery)")
    order_number: str | None = Field(default=None, description="Order number (delivery)")


class LlmMembership(BaseModel):
    """An organization the email's recipient actually belongs to (verbatim from the text)."""

    organization: str = Field(description="The organization's name as written")
    address: str | None = Field(default=None, description="Its street / postal address as written, if given")


class LlmEventOutput(BaseModel):
    """Full structured payload for the events prompt."""

    events: list[LlmEvent] = Field(default_factory=list)
    memberships: list[LlmMembership] = Field(default_factory=list)


class LlmCombinedOutput(BaseModel):
    """Full structured payload for the combined `extract` prompt.

    Every field is always present; a task the request did not ask for just comes
    back empty (the prompt omits its instructions). `build_combined_output_model()`
    produces the *constrained* variant actually sent as `response_format`, with
    entity/relation labels enum-locked exactly like `build_entity_output_model()`.
    """

    entities: list[LlmEntity] = Field(default_factory=list)
    relations: list[LlmRelation] = Field(default_factory=list)
    events: list[LlmEvent] = Field(default_factory=list)
    memberships: list[LlmMembership] = Field(default_factory=list)


@lru_cache(maxsize=32)
def build_combined_output_model(labels: tuple[str, ...], relation_labels: tuple[str, ...]) -> type[BaseModel]:
    """`build_entity_output_model` + an `events` list, for the combined `extract` pack."""
    strict_entities = build_entity_output_model(labels, relation_labels)
    return create_model(
        "LlmCombinedOutputStrict",
        entities=(strict_entities.model_fields["entities"].annotation, Field(default_factory=list)),
        relations=(strict_entities.model_fields["relations"].annotation, Field(default_factory=list)),
        events=(list[LlmEvent], Field(default_factory=list)),
        memberships=(list[LlmMembership], Field(default_factory=list)),
    )


# --------------------------------------------------------------------------- #
# Public results (offsets resolved, enums coerced)                            #
# --------------------------------------------------------------------------- #
class LlmSignatureOutput(BaseModel):
    """What the model reads from the end of an email (every value verbatim from the text)."""

    is_signature: bool = Field(default=False, description="The text ends with an individual's signature block")
    signature: str | None = Field(default=None, description="The signature block, copied exactly")
    person_name: str | None = Field(default=None)
    organizations: list[str] = Field(default_factory=list, description="Broadest first: company, division, team")
    role: str | None = Field(default=None)
    phones: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    websites: list[str] = Field(default_factory=list)
    addresses: list[str] = Field(default_factory=list)


class LlmFileSummary(BaseModel):
    """A short factual summary of one file."""

    summary: str = Field(default="", description="2-4 sentences: what the file is and what it records")


class LlmTableColumn(BaseModel):
    """One column's type and the party it describes."""

    index: int
    field_type: str
    role: str | None = Field(default=None, description="Lowercase English party name, e.g. `sender`")


class LlmTableRelationship(BaseModel):
    """A relationship each row records between two roles."""

    from_role: str
    to_role: str
    verb: str


class LlmTableColumnsOutput(BaseModel):
    """Column typing for the `columns` pack."""

    columns: list[LlmTableColumn] = Field(default_factory=list)
    relationships: list[LlmTableRelationship] = Field(default_factory=list)


@lru_cache(maxsize=8)
def build_table_columns_output_model(field_types: tuple[str, ...], verbs: tuple[str, ...]) -> type[BaseModel]:
    """`LlmTableColumnsOutput` with `field_type` and `verb` enum-locked to the given vocabularies."""
    column_model = create_model(
        "LlmTableColumnStrict",
        index=(int, Field(description="0-based column index")),
        field_type=(Literal[field_types], Field(description="Exactly one of the provided field types")),  # type: ignore
        role=(str | None, Field(default=None, description="Lowercase English party name, or null")),
    )
    relationship_model = create_model(
        "LlmTableRelationshipStrict",
        from_role=(str, Field()),
        to_role=(str, Field()),
        verb=(Literal[verbs], Field(description="Exactly one of the provided verbs")),  # type: ignore
    )
    return create_model(
        "LlmTableColumnsOutputStrict",
        columns=(list[column_model], Field(default_factory=list)),  # type: ignore
        relationships=(list[relationship_model], Field(default_factory=list)),  # type: ignore
    )


class EntityExtraction(BaseModel):
    """Entities + relations, offsets resolved against the analyzed text."""

    entities: list[EntitySpan] = Field(default_factory=list)
    relations: list[RelationSpan] = Field(default_factory=list)


class ParsedEvent(BaseModel):
    """One event with enum-coerced fields, ready for `EventCreate` mapping."""

    title: str
    summary: str | None = None
    event_type: EventType = EventType.OTHER
    date_start: str | None = None
    date_end: str | None = None
    timezone: str | None = None
    is_all_day: bool = False
    date_precision: DatePrecision = DatePrecision.DAY
    status: EventStatus = EventStatus.CONFIRMED
    confidence: float | None = None
    details: EventDetails | None = None
    participants: list[LlmEventParticipant] = Field(default_factory=list)
    places: list[LlmEventPlace] = Field(default_factory=list)


class EventExtraction(BaseModel):
    """Events found in the analyzed text, plus organizations the recipient is confirmed to belong to."""

    events: list[ParsedEvent] = Field(default_factory=list)
    memberships: list[LlmMembership] = Field(
        default_factory=list, description="Verbatim: values the model did not copy from the text are dropped"
    )


class CombinedExtraction(BaseModel):
    """The result of one `extract_all` call: entities/relations + events together."""

    entities: EntityExtraction = Field(default_factory=EntityExtraction)
    events: EventExtraction = Field(default_factory=EventExtraction)


# --------------------------------------------------------------------------- #
# Request bodies                                                              #
# --------------------------------------------------------------------------- #
class EntityRequest(BaseModel):
    """Request body for `POST /entities`."""

    text: str
    labels: list[str] = Field(default_factory=default_ner_labels)
    relation_labels: list[str] = Field(default_factory=default_relation_labels)
    prompt: str | None = Field(
        default=None, description="Override the entities prompt template; the JSON output contract is unchanged"
    )
    model: str | None = Field(default=None, description="Override the configured model id")


class EventRequest(BaseModel):
    """Request body for `POST /events`."""

    text: str
    reference_date: str | None = Field(
        default=None, description="ISO date the text was authored, to anchor relative dates ('next Tuesday')"
    )
    author: str | None = Field(
        default=None, description="Who wrote the text (an email's From), so 'I' / 'we' get a name"
    )
    prompt: str | None = Field(default=None, description="Override the events prompt template")
    model: str | None = Field(default=None, description="Override the configured model id")


class ExtractRequest(BaseModel):
    """Request body for `POST /extract` -- entities/relations + events in one call."""

    text: str
    tasks: list[str] = Field(
        default_factory=lambda: ["entities", "events"], description="Which sections to extract: entities, events"
    )
    labels: list[str] = Field(default_factory=default_ner_labels)
    relation_labels: list[str] = Field(default_factory=default_relation_labels)
    reference_date: str | None = Field(
        default=None, description="ISO date the text was authored, to anchor relative dates"
    )
    author: str | None = Field(
        default=None, description="Who wrote the text (an email's From), so 'I' / 'we' get a name"
    )
    model: str | None = Field(default=None, description="Override the configured model id")


class RunRequest(BaseModel):
    """Request body for `POST /run` -- a fully custom prompt."""

    prompt: str = Field(description="User/instruction prompt; `{text}` is substituted with `text` if present")
    text: str | None = Field(default=None, description="Optional source text substituted into `{text}` in the prompt")
    system: str | None = Field(default=None, description="Optional system message")
    json_schema: dict | None = Field(
        default=None, description="JSON Schema for a structured response; omit for a free-text string response"
    )
    model: str | None = Field(default=None, description="Override the configured model id")
