"""Pure-logic tests for event extraction: timezone-aware parsing + dedup keys."""

from datetime import datetime

from cipher.orchestration.extract_events import (
    _cal_participant,
    _dedup_keys,
    _parse_iso,
    _to_event_create,
)
from cipher.schemas.graph.event import EventSensitivity, EventType
from cipher.schemas.graph.event_participant import EventParticipantRole, RsvpStatus


def test_parse_iso_localizes_naive_to_named_tz():
    dt = _parse_iso("2026-09-15T10:00:00", tz="Europe/Berlin")
    assert dt.utcoffset().total_seconds() == 2 * 3600  # CEST, not UTC
    assert dt.hour == 10


def test_parse_iso_naive_without_tz_falls_back_to_utc():
    dt = _parse_iso("2026-09-15T10:00:00")
    assert dt.utcoffset().total_seconds() == 0


def test_parse_iso_keeps_explicit_offset():
    dt = _parse_iso("2026-09-12T18:05:00-04:00", tz="Europe/Berlin")
    assert dt.utcoffset().total_seconds() == -4 * 3600


def test_dedup_keys_collide_on_uid_or_title_date():
    start = datetime(2026, 9, 15, 10, 0)
    ics = _dedup_keys(title="Weekly sync", date_start=start, event_type=EventType.MEETING, place=None, uid="u-1")
    llm = _dedup_keys(title="weekly  SYNC", date_start=start, event_type=EventType.MEETING, place=None, uid=None)
    assert ics & llm  # same normalized title + day
    assert "uid:u-1" in ics


def test_dedup_keys_place_variant():
    start = datetime(2026, 9, 12, 0, 0)
    a = _dedup_keys(title="Trip A", date_start=start, event_type=EventType.TRAVEL, place="Berlin (BER)", uid=None)
    b = _dedup_keys(
        title="Totally different", date_start=start, event_type=EventType.TRAVEL, place="berlin (ber)", uid=None
    )
    assert a & b


def test_cal_participant_reads_partstat_and_resource():
    from pyparse.parsers.calendar.ics import ParsedCalendarPerson

    person = ParsedCalendarPerson(name="Mark", email="MARK@x.com", partstat="ACCEPTED", cutype="INDIVIDUAL")
    payload = _cal_participant(person, EventParticipantRole.ATTENDEE)
    assert payload.raw_email == "mark@x.com"
    assert payload.rsvp_status == RsvpStatus.ACCEPTED
    assert payload.is_resource is False

    room = ParsedCalendarPerson(name="Room 4", cutype="ROOM")
    assert _cal_participant(room, EventParticipantRole.ATTENDEE).is_resource is True


def test_to_event_create_carries_ical_fields():
    from pyparse.parsers.calendar.ics import ParsedCalendarEvent

    parsed = ParsedCalendarEvent(
        uid="sync-42",
        summary="Weekly sync",
        date_start=datetime(2026, 9, 15, 10, 0),
        event_class="PRIVATE",
        sequence=3,
        recurrence_rule="FREQ=WEEKLY",
        categories=["Work"],
    )
    create = _to_event_create(parsed, dataset_id="d", file_id="f")
    assert create.uid == "sync-42"
    assert create.url is None  # events deliberately do not carry a link
    assert create.sequence == 3
    assert create.recurrence_rule == "FREQ=WEEKLY"
    assert create.categories == ["Work"]
    assert create.sensitivity == EventSensitivity.PRIVATE
