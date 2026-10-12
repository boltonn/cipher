from datetime import UTC, datetime

from pyparse.parsers.calendar.ics import _parse_duration, _unescape_text, parse_events

_FLIGHT = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example//EN
BEGIN:VEVENT
UID:trip-001@example.com
SUMMARY:Flight SFO -> JFK (UA 456)
DESCRIPTION:Confirmation ABC123\\nSeat 14C
LOCATION:San Francisco International Airport
DTSTART:20260905T133000Z
DTEND:20260905T220000Z
STATUS:CONFIRMED
ORGANIZER;CN=United Airlines:mailto:noreply@united.com
ATTENDEE;CN=Nick Bolton:mailto:nick@example.com
CATEGORIES:Travel,Personal
END:VEVENT
END:VCALENDAR
"""

_TZ_AND_ALLDAY = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:hotel-1
SUMMARY:Hotel stay
DTSTART;VALUE=DATE:20260905
DTEND;VALUE=DATE:20260908
END:VEVENT
BEGIN:VEVENT
UID:dinner-1
SUMMARY:Dinner reservation
DTSTART;TZID=America/New_York:20260905T190000
DURATION:PT1H30M
LOCATION:Quince
END:VEVENT
END:VCALENDAR
"""


def test_parses_utc_event_with_participants_and_categories():
    events = parse_events(_FLIGHT.encode())
    assert len(events) == 1
    event = events[0]
    assert event.uid == "trip-001@example.com"
    assert event.summary == "Flight SFO -> JFK (UA 456)"
    assert event.description == "Confirmation ABC123\nSeat 14C"
    assert event.date_start == datetime(2026, 9, 5, 13, 30, tzinfo=UTC)
    assert event.date_end == datetime(2026, 9, 5, 22, 0, tzinfo=UTC)
    assert event.is_all_day is False
    assert event.status == "CONFIRMED"
    assert event.organizer.name == "United Airlines"
    assert event.organizer.email == "noreply@united.com"
    assert [a.name for a in event.attendees] == ["Nick Bolton"]
    assert event.attendees[0].email == "nick@example.com"
    assert event.categories == ["Travel", "Personal"]


_ICAL_RICH = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:sync-42@example.com
SUMMARY:Weekly sync
DTSTART:20260915T100000Z
DTEND:20260915T110000Z
CLASS:PRIVATE
URL:https://example.com/meet/xyz
SEQUENCE:3
GEO:52.5200;13.4050
RRULE:FREQ=WEEKLY;BYDAY=MO
DTSTAMP:20260901T090000Z
LAST-MODIFIED:20260902T120000Z
ORGANIZER;CN=Jane Doe:mailto:jane@example.com
ATTENDEE;CN=Mark Reilly;PARTSTAT=ACCEPTED;CUTYPE=INDIVIDUAL:mailto:mark@example.com
ATTENDEE;CN=Room 4;CUTYPE=ROOM:mailto:room4@example.com
END:VEVENT
END:VCALENDAR
"""


def test_parses_ical_native_fields():
    (event,) = parse_events(_ICAL_RICH.encode())
    assert event.event_class == "PRIVATE"
    assert event.url == "https://example.com/meet/xyz"
    assert event.sequence == 3
    assert event.geo == (52.52, 13.405)
    assert event.recurrence_rule == "FREQ=WEEKLY;BYDAY=MO"
    assert event.date_stamp == datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    assert event.date_source_modified == datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    accepted, room = event.attendees
    assert accepted.partstat == "ACCEPTED" and accepted.cutype == "INDIVIDUAL"
    assert room.cutype == "ROOM"


def test_all_day_and_tzid_and_duration():
    hotel, dinner = parse_events(_TZ_AND_ALLDAY.encode())

    assert hotel.is_all_day is True
    assert hotel.date_start == datetime(2026, 9, 5, 0, 0)
    assert hotel.date_end == datetime(2026, 9, 8, 0, 0)
    assert hotel.date_start.tzinfo is None

    assert dinner.timezone == "America/New_York"
    assert dinner.date_start.utcoffset() is not None  # localized via zoneinfo
    assert dinner.date_end - dinner.date_start == _parse_duration("PT1H30M")
    assert dinner.location == "Quince"


def test_unescape_text():
    assert _unescape_text(r"a\,b\;c\nd\\e") == "a,b;c\nd\\e"


def test_parse_duration_forms():
    assert _parse_duration("PT30M").total_seconds() == 1800
    assert _parse_duration("P1D").days == 1
    assert _parse_duration("-PT1H").total_seconds() == -3600
    assert _parse_duration("garbage") is None


def test_empty_payload_yields_nothing():
    assert parse_events(b"not a calendar") == []
