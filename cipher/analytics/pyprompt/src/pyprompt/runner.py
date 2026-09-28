"""Drive an OpenAI-compatible chat model for structured extraction.

`PromptRunner` is provider-agnostic through the `openai` SDK: set
`LLM__BASE_URL` to reach a local vLLM server or any compatible gateway. It
exposes the two registered tasks (`extract_entities`, `extract_events`) and a
generic `run` for a fully custom prompt.
"""

from __future__ import annotations

import json

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from cipher.schemas.graph.event import (
    DatePrecision,
    DeadlineDetails,
    DeliveryDetails,
    EventStatus,
    EventType,
    LodgingDetails,
    ReservationDetails,
    TravelDetails,
)
from cipher.schemas.graph.ontology import default_ner_labels, default_relation_labels
from pyprompt.errors import StructuredOutputError
from pyprompt.offsets import OffsetResolver
from pyprompt.prompts.registry import ENTITIES, EVENTS, EXTRACT, get_pack
from pyprompt.schemas import (
    CombinedExtraction,
    EntityExtraction,
    EntitySpan,
    EventExtraction,
    LlmEventOutput,
    ParsedEvent,
    RelationSpan,
    build_combined_output_model,
    build_entity_output_model,
)
from pyprompt.settings import Settings
from pyprompt.templating import render_custom


def _enum_or[T](default: T, value: str | None, enum_cls: type) -> T:
    """Coerce a model-supplied string to an enum member, falling back to `default`."""
    if not value:
        return default
    try:
        return enum_cls(value.strip().lower())
    except ValueError:
        return default


class PromptRunner:
    """A configured client plus the task methods that use it."""

    def __init__(self, settings: Settings):
        self._settings = settings
        llm = settings.llm
        client_kwargs = llm.openai_client_kwargs()
        self._client = AsyncOpenAI(timeout=settings.request_timeout, **client_kwargs)
        self._model = llm.model
        logger.info(
            f"✅ pyprompt runner ready (provider={llm.provider}, model={self._model}, "
            f"base_url={client_kwargs.get('base_url', 'default')})."
        )

    # ---- registered tasks ------------------------------------------------- #
    async def extract_entities(
        self,
        text: str,
        *,
        labels: list[str] | None = None,
        relation_labels: list[str] | None = None,
        prompt: str | None = None,
        model: str | None = None,
    ) -> EntityExtraction:
        """Run the entities/relations pack and resolve offsets into `text`."""
        labels = labels or default_ner_labels()
        relation_labels = relation_labels or default_relation_labels()
        clipped = text[: self._settings.max_input_chars]

        template = get_pack(ENTITIES).load()
        system, user = template.render(text=clipped, labels=labels, relation_labels=relation_labels)
        if prompt:
            user = render_custom(prompt, clipped)

        # `label` fields are enum-locked to this exact vocabulary in the schema,
        # so the model cannot emit a paraphrase we'd have to guess at downstream.
        output_model = build_entity_output_model(tuple(labels), tuple(relation_labels))
        raw = await self._structured(system=system, user=user, model_cls=output_model, model=model)
        return _resolve_entity_spans(raw, clipped)

    async def extract_events(
        self,
        text: str,
        *,
        reference_date: str | None = None,
        prompt: str | None = None,
        model: str | None = None,
    ) -> EventExtraction:
        """Run the events pack; enum-coerce each event's fields."""
        clipped = text[: self._settings.max_input_chars]

        template = get_pack(EVENTS).load()
        system, user = template.render(text=clipped, reference_date=reference_date)
        if prompt:
            user = render_custom(prompt, clipped)

        raw = await self._structured(system=system, user=user, model_cls=LlmEventOutput, model=model)
        return EventExtraction(events=[_coerce_event(e) for e in raw.events])

    async def extract_all(
        self,
        text: str,
        *,
        tasks: set[str] | list[str] = ("entities", "events"),
        labels: list[str] | None = None,
        relation_labels: list[str] | None = None,
        reference_date: str | None = None,
        model: str | None = None,
    ) -> CombinedExtraction:
        """Run the combined `extract` pack -- entities/relations and/or events in one call.

        `tasks` selects which sections the prompt asks for; an unrequested section
        comes back empty. Offsets are resolved and event enums coerced exactly as
        the single-task methods do.
        """
        task_set = {t.strip().lower() for t in tasks}
        labels = labels or default_ner_labels()
        relation_labels = relation_labels or default_relation_labels()
        clipped = text[: self._settings.max_input_chars]

        template = get_pack(EXTRACT).load()
        system, user = template.render(
            text=clipped,
            tasks=sorted(task_set),
            labels=labels,
            relation_labels=relation_labels,
            reference_date=reference_date,
        )
        # Entity/relation `label` fields are enum-locked to the ontology vocabulary
        # (same as `extract_entities`); `events` stays permissive and is coerced.
        output_model = build_combined_output_model(tuple(labels), tuple(relation_labels))
        raw = await self._structured(system=system, user=user, model_cls=output_model, model=model)

        entities = _resolve_entity_spans(raw, clipped) if "entities" in task_set else EntityExtraction()
        events = (
            EventExtraction(events=[_coerce_event(e) for e in raw.events])
            if "events" in task_set
            else EventExtraction()
        )
        return CombinedExtraction(entities=entities, events=events)

    async def run(
        self,
        *,
        prompt: str,
        text: str | None = None,
        system: str | None = None,
        json_schema: dict | None = None,
        model: str | None = None,
    ) -> dict:
        """Run a fully custom prompt. With `json_schema`, returns the parsed object; else `{'text': ...}`."""
        user = render_custom(prompt, text)
        messages = _messages(system, user)

        if json_schema is None:
            completion = await self._client.chat.completions.create(
                model=model or self._model,
                messages=messages,
                temperature=self._settings.temperature,
            )
            return {"text": completion.choices[0].message.content or ""}

        response_format = {
            "type": "json_schema",
            "json_schema": {"name": "custom", "schema": json_schema, "strict": False},
        }
        completion = await self._client.chat.completions.create(
            model=model or self._model,
            messages=messages,
            temperature=self._settings.temperature,
            response_format=response_format,
        )
        content = completion.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError(f"Custom prompt did not return valid JSON: {exc}") from exc

    # ---- internals ------------------------------------------------------- #
    async def _structured[M: BaseModel](self, *, system: str, user: str, model_cls: type[M], model: str | None) -> M:
        """Call the model with a Pydantic `response_format`, retrying on a schema miss."""
        messages = _messages(system, user)
        last_error = ""
        for attempt in range(self._settings.max_retries + 1):
            completion = await self._client.chat.completions.parse(
                model=model or self._model,
                messages=messages,
                temperature=self._settings.temperature,
                response_format=model_cls,
            )
            message = completion.choices[0].message
            if message.refusal:
                last_error = f"model refused: {message.refusal}"
            elif message.parsed is not None:
                return message.parsed
            else:
                try:
                    return model_cls.model_validate_json(message.content or "")
                except ValidationError as exc:
                    last_error = str(exc)

            logger.warning(f"pyprompt structured attempt {attempt + 1} failed: {last_error}")
            messages = [
                *messages,
                {
                    "role": "user",
                    "content": f"That response was invalid ({last_error}). Reply again as valid JSON only.",
                },
            ]

        raise StructuredOutputError(
            f"No schema-valid response after {self._settings.max_retries + 1} attempts: {last_error}"
        )


def _messages(system: str | None, user: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    return messages


def _resolve_entity_spans(raw: BaseModel, source: str) -> EntityExtraction:
    """Turn offset-free model output into `EntitySpan` / `RelationSpan` grounded in `source`.

    Accepts either `LlmEntityOutput` or the enum-locked variant from
    `build_entity_output_model` -- both expose the same `entities` / `relations`
    fields with `surface_text` / `label` / `head_text` / `tail_text`.
    """
    resolver = OffsetResolver(source)
    spans: list[EntitySpan] = []
    surface_to_starts: dict[str, list[int]] = {}
    for item in raw.entities:
        located = resolver.locate(item.surface_text)
        if located is None:
            continue
        start, end = located
        spans.append(
            EntitySpan(
                surface_text=item.surface_text,
                label=item.label.strip().lower(),
                start_offset=start,
                end_offset=end,
            )
        )
        surface_to_starts.setdefault(item.surface_text.strip(), []).append(start)

    relations: list[RelationSpan] = []
    for rel in raw.relations:
        pair = _closest_pair(
            surface_to_starts.get(rel.head_text.strip(), []),
            surface_to_starts.get(rel.tail_text.strip(), []),
        )
        if pair is None:
            continue
        head_start, tail_start = pair
        relations.append(
            RelationSpan(
                label=rel.label.strip().lower(),
                head_text=rel.head_text,
                tail_text=rel.tail_text,
                head_start=head_start,
                tail_start=tail_start,
            )
        )
    return EntityExtraction(entities=spans, relations=relations)


def _closest_pair(heads: list[int], tails: list[int]) -> tuple[int, int] | None:
    """The (head_start, tail_start) with the smallest gap.

    Binds a relation to the nearest occurrences when a surface form appears more
    than once. None if either side never resolved.
    """
    if not heads or not tails:
        return None
    return min(((h, t) for h in heads for t in tails if h != t), key=lambda p: abs(p[0] - p[1]), default=None)


_DETAIL_FIELDS: dict[EventType, tuple[type, tuple[str, ...]]] = {
    EventType.TRAVEL: (TravelDetails, ("operator", "number", "confirmation")),
    EventType.LODGING: (LodgingDetails, ("operator", "confirmation", "nights", "guests")),
    EventType.RESERVATION: (ReservationDetails, ("operator", "confirmation", "party_size")),
    EventType.DEADLINE: (DeadlineDetails, ("amount", "currency", "payee")),
    EventType.DELIVERY: (DeliveryDetails, ("carrier", "tracking_number", "order_number")),
}


def _build_details(event_type: EventType, event) -> BaseModel | None:
    """Assemble the typed `details` member for `event_type` from the flat `LlmEvent` fields.

    Returns None when the type carries no detail row or the model supplied nothing
    usable for it (a bad value -- e.g. a non-ISO currency -- drops the whole blob).
    """
    spec = _DETAIL_FIELDS.get(event_type)
    if spec is None:
        return None
    model_cls, fields = spec
    values = {name: getattr(event, name, None) for name in fields}
    if not any(v is not None for v in values.values()):
        return None
    try:
        return model_cls(**values)
    except ValidationError:
        return None


def _coerce_event(event) -> ParsedEvent:
    """Map one `LlmEvent` to a `ParsedEvent` with enum fields and a typed `details` blob."""
    event_type = _enum_or(EventType.OTHER, event.event_type, EventType)
    return ParsedEvent(
        title=event.title,
        summary=event.summary,
        event_type=event_type,
        date_start=event.date_start,
        date_end=event.date_end,
        timezone=event.timezone,
        is_all_day=event.is_all_day,
        date_precision=_enum_or(DatePrecision.DAY, event.date_precision, DatePrecision),
        status=_enum_or(EventStatus.CONFIRMED, event.status, EventStatus),
        confidence=_clamp01(event.confidence),
        details=_build_details(event_type, event),
        participants=event.participants,
        places=event.places,
    )


def _clamp01(value: float | None) -> float | None:
    """Keep a model-supplied confidence inside [0, 1]; None stays None."""
    if value is None:
        return None
    return max(0.0, min(1.0, value))
