"""The combined `extract` pack: task-gated prompt sections + `extract_all` fan-out."""

import pytest
from pyprompt.prompts.registry import EXTRACT, get_pack
from pyprompt.runner import _coerce_event, _resolve_entity_spans
from pyprompt.schemas import CombinedExtraction, EntityExtraction, LlmCombinedOutput, LlmEntity, LlmEvent

_ENTITIES_MARKER = "Named entities and relations"
_EVENTS_MARKER = "Dated events"


@pytest.mark.parametrize(
    "tasks, wants_entities, wants_events",
    [
        (["entities", "events"], True, True),
        (["entities"], True, False),
        (["events"], False, True),
    ],
)
def test_pack_includes_only_requested_sections(tasks, wants_entities, wants_events):
    template = get_pack(EXTRACT).load()
    system, user = template.render(
        text="hello", tasks=sorted(tasks), labels=["person"], relation_labels=["member of"], reference_date=None
    )
    assert (_ENTITIES_MARKER in system) is wants_entities
    assert (_EVENTS_MARKER in system) is wants_events
    assert "hello" in user


def _fan_out(raw: LlmCombinedOutput, tasks: set[str]) -> CombinedExtraction:
    """Mirror runner.extract_all's post-processing without an LLM call."""
    from pyprompt.schemas import EventExtraction, LlmEntityOutput

    entities = (
        _resolve_entity_spans(LlmEntityOutput(entities=raw.entities, relations=raw.relations), "Ada met Bob.")
        if "entities" in tasks
        else EntityExtraction()
    )
    events = EventExtraction(events=[_coerce_event(e) for e in raw.events]) if "events" in tasks else EventExtraction()
    return CombinedExtraction(entities=entities, events=events)


def test_fan_out_populates_both_when_both_requested():
    raw = LlmCombinedOutput(
        entities=[LlmEntity(surface_text="Ada", label="person"), LlmEntity(surface_text="Bob", label="person")],
        events=[LlmEvent(title="Sync", event_type="meeting", date_start="2026-09-15")],
    )
    out = _fan_out(raw, {"entities", "events"})
    assert [s.surface_text for s in out.entities.entities] == ["Ada", "Bob"]
    assert len(out.events.events) == 1


def test_fan_out_drops_unrequested_task():
    raw = LlmCombinedOutput(
        entities=[LlmEntity(surface_text="Ada", label="person")],
        events=[LlmEvent(title="Sync", event_type="meeting", date_start="2026-09-15")],
    )
    out = _fan_out(raw, {"events"})
    assert out.entities.entities == []
    assert len(out.events.events) == 1
