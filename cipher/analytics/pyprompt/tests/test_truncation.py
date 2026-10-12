import pytest
from pyprompt.errors import StructuredOutputError
from pyprompt.runner import _complete_prefix
from pyprompt.schemas import LlmCombinedOutput, LlmEventOutput

_TWO_EVENTS = (
    '{"events":[{"title":"Flight to Paris","event_type":"travel","date_start":"2013-01-10",'
    '"participants":[{"name":"Nick","role":"traveler"}]},'
    '{"title":"Train to Nantes","event_type":"travel","date_start":"2013-01-12"}]}'
)


def test_complete_output_is_kept_whole():
    assert [e.title for e in _complete_prefix(LlmEventOutput, _TWO_EVENTS).events] == [
        "Flight to Paris",
        "Train to Nantes",
    ]


@pytest.mark.parametrize("cut_inside", ['"Train to Nan', '"date_start":"2013-01-1', '"event_type":'])
def test_the_event_being_written_is_dropped_not_kept_half_done(cut_inside):
    cut = _TWO_EVENTS[: _TWO_EVENTS.rindex(cut_inside) + len(cut_inside)]
    events = _complete_prefix(LlmEventOutput, cut).events
    assert [e.title for e in events] == ["Flight to Paris"]
    assert events[0].participants[0].name == "Nick"


def test_cut_inside_the_first_event_keeps_nothing():
    cut = _TWO_EVENTS[: _TWO_EVENTS.index('"role":"trav') + 12]
    assert _complete_prefix(LlmEventOutput, cut).events == []


def test_earlier_sections_survive_a_cut_in_a_later_one():
    cut = (
        '{"entities":[{"surface_text":"Nick","label":"person"}],"relations":[],'
        '"events":[{"title":"A","event_type":"travel"},{"title":"B'
    )
    output = _complete_prefix(LlmCombinedOutput, cut)
    assert [e.surface_text for e in output.entities] == ["Nick"]
    assert [e.title for e in output.events] == ["A"]


def test_unusable_output_still_raises():
    with pytest.raises(StructuredOutputError, match="token cap"):
        _complete_prefix(LlmEventOutput, "not json")
