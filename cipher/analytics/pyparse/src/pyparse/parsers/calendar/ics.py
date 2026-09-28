"""Stateless parser for iCalendar (`.ics` / RFC 5545) data.

Mirrors ``pyparse.parsers.contacts.vcard`` in style: a hand-rolled line
unfolder + property parser, no third-party iCal library. It surfaces each
``VEVENT`` as a ``ParsedCalendarEvent`` -- a thin, parser-local intermediate.
Mapping that onto CIPHER's ``EventCreate`` (attaching ``dataset_id`` /
``file_id`` and resolving who/where) is an orchestration concern, not this
parser's.

Handled: line unfolding, ``TEXT`` value unescaping, ``DTSTART`` / ``DTEND`` in
UTC (``...Z``), floating local time with ``TZID=``, and all-day
(``VALUE=DATE``), ``DURATION`` as a fallback for ``DTEND``, ``STATUS``,
``ORGANIZER`` / ``ATTENDEE`` (``mailto:`` and ``CN=`` pulled out), ``RRULE``,
``CATEGORIES``.
"""

from __future__ import annotations

import io
import re
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from loguru import logger
from pydantic import BaseModel, Field

_DURATION_RE = re.compile(
    r"^(?P<sign>[+-])?P"
    r"(?:(?P<weeks>\d+)W)?"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


class ParsedCalendarPerson(BaseModel):
    """An ``ORGANIZER`` / ``ATTENDEE`` cal-address with its parameters."""

    name: str | None = Field(default=None, description="CN= display name")
    email: str | None = Field(default=None, description="mailto: address, lowercased")
    partstat: str | None = Field(default=None, description="PARTSTAT= (NEEDS-ACTION | ACCEPTED | DECLINED | ...)")
    cutype: str | None = Field(default=None, description="CUTYPE= (INDIVIDUAL | GROUP | ROOM | RESOURCE | UNKNOWN)")

    @property
    def display(self) -> str | None:
        """Best surface string: the display name, else the address."""
        return self.name or self.email


class ParsedCalendarEvent(BaseModel):
    """One ``VEVENT`` as read from an `.ics` payload."""

    uid: str | None = None
    summary: str | None = None
    description: str | None = None
    location: str | None = Field(default=None, description="Free-text LOCATION value")
    geo: tuple[float, float] | None = Field(default=None, description="(latitude, longitude) from GEO")
    url: str | None = Field(default=None, description="URL value")
    date_start: datetime | None = None
    date_end: datetime | None = None
    timezone: str | None = Field(default=None, description="IANA TZID carried on DTSTART, if any")
    is_all_day: bool = False
    status: str | None = Field(default=None, description="CONFIRMED | TENTATIVE | CANCELLED")
    event_class: str | None = Field(default=None, description="CLASS (PUBLIC | PRIVATE | CONFIDENTIAL)")
    sequence: int | None = Field(default=None, description="SEQUENCE revision number")
    date_stamp: datetime | None = Field(default=None, description="DTSTAMP")
    date_source_created: datetime | None = Field(default=None, description="CREATED")
    date_source_modified: datetime | None = Field(default=None, description="LAST-MODIFIED")
    organizer: ParsedCalendarPerson | None = None
    attendees: list[ParsedCalendarPerson] = Field(default_factory=list)
    recurrence_rule: str | None = None
    categories: list[str] = Field(default_factory=list)


def _unescape_text(value: str) -> str:
    r"""Unescape an RFC 5545 TEXT value (``\n``, ``\,``, ``\;``, ``\\``)."""
    out: list[str] = []
    it = iter(value)
    for ch in it:
        if ch != "\\":
            out.append(ch)
            continue
        nxt = next(it, "")
        if nxt in ("n", "N"):
            out.append("\n")
        elif nxt in (",", ";", "\\"):
            out.append(nxt)
        else:
            out.append(nxt)
    return "".join(out)


def _parse_params(raw: str) -> dict[str, str]:
    """`;TZID=America/New_York;VALUE=DATE` -> {'TZID': ..., 'VALUE': 'DATE'}."""
    params: dict[str, str] = {}
    for part in raw.split(";"):
        if "=" in part:
            key, _, val = part.partition("=")
            params[key.strip().upper()] = val.strip().strip('"')
    return params


def _parse_datetime(value: str, params: dict[str, str]) -> tuple[datetime | None, str | None, bool]:
    """Return (datetime, tzid, is_all_day) for a DTSTART/DTEND value."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or (len(value) == 8 and value.isdigit()):
        try:
            return datetime.strptime(value[:8], "%Y%m%d"), None, True
        except ValueError:
            return None, None, False

    fmt = "%Y%m%dT%H%M%S"
    if value.endswith("Z"):
        try:
            return datetime.strptime(value[:-1], fmt).replace(tzinfo=UTC), None, False
        except ValueError:
            return None, None, False

    tzid = params.get("TZID")
    try:
        naive = datetime.strptime(value, fmt)
    except ValueError:
        return None, None, False
    if tzid:
        try:
            return naive.replace(tzinfo=ZoneInfo(tzid)), tzid, False
        except (ZoneInfoNotFoundError, ValueError):
            logger.debug(f"Unknown TZID {tzid!r}; keeping naive datetime")
    return naive, tzid, False


def _parse_duration(value: str) -> timedelta | None:
    """ISO-8601 duration (`PT1H30M`, `P2D`) -> timedelta."""
    match = _DURATION_RE.match(value.strip())
    if not match:
        return None
    parts = {k: int(v) for k, v in match.groupdict().items() if v and k != "sign"}
    delta = timedelta(
        weeks=parts.get("weeks", 0),
        days=parts.get("days", 0),
        hours=parts.get("hours", 0),
        minutes=parts.get("minutes", 0),
        seconds=parts.get("seconds", 0),
    )
    return -delta if match.group("sign") == "-" else delta


def _parse_cal_person(value: str, params: dict[str, str]) -> ParsedCalendarPerson:
    """An ``ORGANIZER`` / ``ATTENDEE`` value + params -> `ParsedCalendarPerson`."""
    raw = value.strip()
    email = raw.split(":", 1)[-1].strip() if raw.lower().startswith("mailto:") else raw
    email = email.lower() or None
    return ParsedCalendarPerson(
        name=params.get("CN") or None,
        email=email,
        partstat=(params.get("PARTSTAT") or "").upper() or None,
        cutype=(params.get("CUTYPE") or "").upper() or None,
    )


def _parse_geo(value: str) -> tuple[float, float] | None:
    """``GEO`` value ``lat;lon`` (or ``lat,lon``) -> ``(lat, lon)``."""
    parts = re.split(r"[;,]", value.strip(), maxsplit=1)
    if len(parts) != 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


class IcsParser:
    """Parser for iCalendar (`.ics`) payloads."""

    @staticmethod
    def _unfold(stream: io.TextIOBase) -> Generator[str, None, None]:
        buffer = ""
        for line in stream:
            if not line:
                continue
            if line[0] in (" ", "\t"):
                buffer += line[1:].rstrip("\r\n")
            else:
                if buffer:
                    yield buffer
                buffer = line.rstrip("\r\n")
        if buffer:
            yield buffer

    @staticmethod
    def _split_line(line: str) -> tuple[str, dict[str, str], str]:
        head, _, value = line.partition(":")
        name, _, raw_params = head.partition(";")
        return name.strip().upper(), _parse_params(raw_params), value

    @classmethod
    def stream(cls, stream: BinaryIO, encoding: str = "utf-8") -> Generator[ParsedCalendarEvent, None, None]:
        """Yield each VEVENT from an `.ics` byte stream."""
        text_stream = io.TextIOWrapper(stream, encoding=encoding, errors="ignore", newline="")
        current: dict | None = None
        try:
            for line in cls._unfold(text_stream):
                name, params, value = cls._split_line(line)

                if name == "BEGIN" and value.strip().upper() == "VEVENT":
                    current = {"attendees": [], "categories": []}
                    continue
                if name == "END" and value.strip().upper() == "VEVENT":
                    if current is not None:
                        yield cls._build(current)
                    current = None
                    continue
                if current is None:
                    continue

                cls._apply(current, name, params, value)
        finally:
            text_stream.detach()

    @staticmethod
    def _apply(current: dict, name: str, params: dict[str, str], value: str) -> None:
        match name:
            case "UID":
                current["uid"] = value.strip()
            case "SUMMARY":
                current["summary"] = _unescape_text(value)
            case "DESCRIPTION":
                current["description"] = _unescape_text(value)
            case "LOCATION":
                current["location"] = _unescape_text(value)
            case "DTSTART":
                dt, tzid, all_day = _parse_datetime(value, params)
                current["date_start"], current["timezone"], current["is_all_day"] = dt, tzid, all_day
            case "DTEND":
                dt, _, _ = _parse_datetime(value, params)
                current["date_end"] = dt
            case "DURATION":
                current["_duration"] = _parse_duration(value)
            case "STATUS":
                current["status"] = value.strip().upper()
            case "CLASS":
                current["event_class"] = value.strip().upper()
            case "URL":
                current["url"] = value.strip()
            case "GEO":
                current["geo"] = _parse_geo(value)
            case "SEQUENCE":
                try:
                    current["sequence"] = int(value.strip())
                except ValueError:
                    pass
            case "DTSTAMP":
                current["date_stamp"], _, _ = _parse_datetime(value, params)
            case "CREATED":
                current["date_source_created"], _, _ = _parse_datetime(value, params)
            case "LAST-MODIFIED":
                current["date_source_modified"], _, _ = _parse_datetime(value, params)
            case "ORGANIZER":
                current["organizer"] = _parse_cal_person(value, params)
            case "ATTENDEE":
                current["attendees"].append(_parse_cal_person(value, params))
            case "RRULE":
                current["recurrence_rule"] = value.strip()
            case "CATEGORIES":
                current["categories"].extend(part.strip() for part in value.split(",") if part.strip())

    @staticmethod
    def _build(current: dict) -> ParsedCalendarEvent:
        if current.get("date_end") is None and current.get("date_start") is not None and current.get("_duration"):
            current["date_end"] = current["date_start"] + current["_duration"]
        current.pop("_duration", None)
        return ParsedCalendarEvent.model_validate(current)

    @classmethod
    def parse(cls, file: bytes | str | Path, encoding: str = "utf-8") -> list[ParsedCalendarEvent]:
        """Read every VEVENT from an `.ics` file path or byte payload."""
        if isinstance(file, bytes):
            return list(cls.stream(io.BytesIO(file), encoding))
        with open(file, "rb") as handle:
            return list(cls.stream(handle, encoding))
