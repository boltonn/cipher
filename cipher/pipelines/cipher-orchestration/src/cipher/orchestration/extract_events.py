"""Calendar-event extraction workflows (EVENT_EXTRACTION enrichment).

Two producers, both writing `event` rows plus *unresolved* `event_participant`
(`raw_name` / `raw_email`) and `event_place` (`raw_text`) links that
`resolve-event-links` later resolves:

* **`.ics` (deterministic)** -- `extract_events_workflow`. Parses a dataset's
  `text/calendar` files (`pyparse.parsers.calendar.ics`); one `VEVENT` -> one
  event (`extractor = "ics"`), carrying the iCalendar fields losslessly (`uid`,
  `recurrence_rule`, `categories`, `sequence`, `url`, `sensitivity`, source
  timestamps; `GEO` -> a geocoded `event_place`). No model.
* **free text (LLM)** -- `extract_text_events_workflow`. Runs `pyprompt` over a
  dataset's email (and, with `--docs`, document) bodies anchored to the file's
  authored date; each event it finds -> one row (`extractor = "llm"`,
  `extraction_model` set), with typed `details` / `url` / `confidence`, deduped
  against existing rows on `uid` then `(title, start date)` /
  `(type, start date, place)`. Opt-in (`cipher extract-events --llm`).

The LLM is too slow to read every file, so a **gate** runs first
(`gate_text_events_workflow`): a zero-shot classifier scores each text for "a
person is taking part in something", the score lands on the file as
`tag_scores["event"]`, and files under the threshold are SKIPPED -- except a small deterministic sample
that still goes to the LLM, so what the gate misses can be measured
(`get_event_gate_report`). Every file the LLM reads is then tagged on `file`:
`event` in `tags` when it found one, in `negative_tags` when it did not --
labels for training a faster first pass later.

Re-runnable: a file with a completed EVENT_EXTRACTION row is skipped until
`reset-events` clears it (which drops both `ics` and `llm` rows).
"""

import asyncio
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from loguru import logger
from sqlalchemy import Float, func, select
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresEventRepository,
    PostgresExtractedTextRepository,
    PostgresFileRepository,
    PostgresLocationRepository,
)
from cipher.datastores.postgres.tables.enrichment import EnrichmentTable
from cipher.datastores.postgres.tables.event import EventTable
from cipher.datastores.postgres.tables.event_place import EventPlaceTable
from cipher.datastores.postgres.tables.extracted_text import ExtractedTextTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.utils import normalize_name
from cipher.schemas._base.common import ModelTagType
from cipher.schemas.content.email import EmailCategory, EmailClient, EmailState
from cipher.schemas.graph.event import (
    EVENT_FILE_TAG,
    DatePrecision,
    EventCreate,
    EventSensitivity,
    EventStatus,
    EventType,
)
from cipher.schemas.graph.event_participant import EventParticipantCreate, EventParticipantRole, RsvpStatus
from cipher.schemas.graph.event_place import EventPlaceCreate, EventPlaceRole
from cipher.schemas.graph.location import LocationCreate
from cipher.schemas.graph.ontology import LocationSource
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType, ProcessingStatus
from cipher.schemas.interaction.tag import TagSource
from cipher.utils.io import fetch_bytes_from_uri

if TYPE_CHECKING:
    from pyparse.parsers.calendar.ics import ParsedCalendarEvent, ParsedCalendarPerson
    from pyprompt.schemas import ParsedEvent
    from sqlalchemy.ext.asyncio import AsyncSession

_EXTRACTOR = "ics"
_LLM_EXTRACTOR = "llm"
_EMAIL_FILETYPE_GROUP = "email"
_DOCUMENT_FILETYPE_GROUP = "document"
_CALENDAR_MIME = "text/calendar"
_CALENDAR_FILETYPE = "ics"

# The filetype groups the LLM event pass scans, in order.
TEXT_EVENT_GROUPS_EMAIL: tuple[str, ...] = (_EMAIL_FILETYPE_GROUP,)
TEXT_EVENT_GROUPS_ALL: tuple[str, ...] = (_EMAIL_FILETYPE_GROUP, _DOCUMENT_FILETYPE_GROUP)

_STATUS_MAP = {
    "CONFIRMED": EventStatus.CONFIRMED,
    "TENTATIVE": EventStatus.TENTATIVE,
    "CANCELLED": EventStatus.CANCELLED,
}

_SENSITIVITY_MAP = {
    "PUBLIC": EventSensitivity.PUBLIC,
    "PRIVATE": EventSensitivity.PRIVATE,
    "CONFIDENTIAL": EventSensitivity.CONFIDENTIAL,
}

_PARTSTAT_MAP = {
    "NEEDS-ACTION": RsvpStatus.NEEDS_ACTION,
    "ACCEPTED": RsvpStatus.ACCEPTED,
    "DECLINED": RsvpStatus.DECLINED,
    "TENTATIVE": RsvpStatus.TENTATIVE,
    "DELEGATED": RsvpStatus.DELEGATED,
}

_RESOURCE_CUTYPES = {"ROOM", "RESOURCE"}

_TYPE_KEYWORDS: tuple[tuple[EventType, tuple[str, ...]], ...] = (
    (EventType.TRAVEL, ("flight", "train", "airline", "rail", "boarding", "rental car", "car rental")),
    (EventType.LODGING, ("hotel", "lodging", "check-in", "check in", "checkin", "airbnb", "stay")),
    (EventType.RESERVATION, ("reservation", "dinner", "lunch", "table", "booking")),
    (EventType.DELIVERY, ("delivery", "shipment", "package", "arriving")),
    (EventType.GATHERING, ("conference", "summit", "wedding", "party", "ceremony", "festival", "reunion")),
    (EventType.MEETING, ("meeting", "call", "sync", "1:1", "standup", "interview")),
)


def _infer_type(parsed: "ParsedCalendarEvent") -> EventType:
    """Best-effort event type from CATEGORIES + SUMMARY keywords."""
    haystack = " ".join([*parsed.categories, parsed.summary or ""]).lower()
    for event_type, needles in _TYPE_KEYWORDS:
        if any(needle in haystack for needle in needles):
            return event_type
    return EventType.OTHER


def _aware(value: datetime | None) -> datetime | None:
    """Coerce a naive datetime to UTC so it stores in a timestamptz column."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _to_event_create(parsed: "ParsedCalendarEvent", *, dataset_id: str, file_id: str) -> EventCreate | None:
    """Map one parsed VEVENT to an `EventCreate`; None when it has no start."""
    if parsed.date_start is None:
        return None
    return EventCreate(
        dataset_id=dataset_id,
        file_id=file_id,
        event_type=_infer_type(parsed),
        title=(parsed.summary or "Untitled event")[:512],
        summary=parsed.description,
        date_start=_aware(parsed.date_start),
        date_end=_aware(parsed.date_end),
        timezone=parsed.timezone,
        is_all_day=parsed.is_all_day,
        date_precision=DatePrecision.DAY if parsed.is_all_day else DatePrecision.EXACT,
        status=_STATUS_MAP.get(parsed.status or "", EventStatus.CONFIRMED),
        categories=parsed.categories,
        sensitivity=_SENSITIVITY_MAP.get(parsed.event_class or ""),
        uid=parsed.uid,
        recurrence_rule=parsed.recurrence_rule,
        sequence=parsed.sequence,
        source_created=_aware(parsed.date_source_created or parsed.date_stamp),
        source_last_modified=_aware(parsed.date_source_modified),
        extractor=_EXTRACTOR,
    )


def _cal_participant(person: "ParsedCalendarPerson", role: EventParticipantRole) -> EventParticipantCreate | None:
    """Map an `.ics` ORGANIZER/ATTENDEE to an unresolved `EventParticipantCreate`."""
    name = (person.name or "").strip() or None
    email = (person.email or "").strip().lower() or None
    if not name and not email:
        return None
    return EventParticipantCreate(
        raw_name=name,
        raw_email=email,
        role=role,
        rsvp_status=_PARTSTAT_MAP.get(person.partstat or ""),
        is_resource=(person.cutype or "") in _RESOURCE_CUTYPES,
    )


async def _extract_calendar_file(
    file_resource: dict,
    event_repo: PostgresEventRepository,
    location_repo: PostgresLocationRepository,
) -> int:
    """Parse one `.ics` file into event rows (+ unresolved participant/place links). Returns events written."""
    from pyparse.parsers.calendar.ics import IcsParser

    file_id = file_resource["id"]
    dataset_id = file_resource["dataset_id"]

    payload = fetch_bytes_from_uri(file_resource["uri"])
    written = 0
    for parsed in IcsParser.parse(payload):
        create = _to_event_create(parsed, dataset_id=dataset_id, file_id=file_id)
        if create is None:
            continue
        event = await event_repo.add_event(create)

        people = [(parsed.organizer, EventParticipantRole.ORGANIZER)] if parsed.organizer else []
        people += [(person, EventParticipantRole.ATTENDEE) for person in parsed.attendees]
        for person, role in people:
            payload = _cal_participant(person, role)
            if payload is not None:
                await event_repo.add_participant(event_id=event.id, payload=payload)

        await _attach_calendar_place(
            parsed,
            event_id=event.id,
            dataset_id=dataset_id,
            file_id=file_id,
            event_repo=event_repo,
            location_repo=location_repo,
        )
        written += 1
    return written


async def _attach_calendar_place(
    parsed: "ParsedCalendarEvent",
    *,
    event_id: str,
    dataset_id: str,
    file_id: str,
    event_repo: PostgresEventRepository,
    location_repo: PostgresLocationRepository,
) -> None:
    """Attach the VEVENT's place: a geocoded `location` when `GEO` is present, else raw `LOCATION` text."""
    venue = (parsed.location or "").strip() or None
    if parsed.geo is not None:
        latitude, longitude = parsed.geo
        location = await location_repo.add_location(
            LocationCreate(
                dataset_id=dataset_id,
                file_id=file_id,
                latitude=latitude,
                longitude=longitude,
                name=venue,
                source=LocationSource.NAME_MENTION,
            )
        )
        await event_repo.add_place(
            event_id=event_id,
            payload=EventPlaceCreate(location_id=location.id, raw_text=venue, role=EventPlaceRole.VENUE),
        )
    elif venue:
        await event_repo.add_place(event_id=event_id, payload=EventPlaceCreate(raw_text=venue))


async def queue_event_extraction_enrichments(session: "AsyncSession", dataset_id: str) -> int:
    """Queue EVENT_EXTRACTION enrichments for a dataset's calendar files (mime `text/calendar`)."""
    stmt = (
        select(FileTable)
        .outerjoin(
            EnrichmentTable,
            (EnrichmentTable.enrichable_id == FileTable.id)
            & (EnrichmentTable.enrichable_type == EnrichableType.FILE)
            & (EnrichmentTable.enrichment_type == EnrichmentType.EVENT_EXTRACTION),
        )
        .where(
            EnrichmentTable.id.is_(None),
            FileTable.dataset_id == dataset_id,
            FileTable.mime_type == _CALENDAR_MIME,
        )
    )
    files = (await session.execute(stmt)).scalars().all()
    for file in files:
        session.add(
            EnrichmentTable(
                enrichable_type=EnrichableType.FILE,
                enrichable_id=file.id,
                enrichment_type=EnrichmentType.EVENT_EXTRACTION,
                status=ProcessingStatus.PENDING,
            )
        )
    await session.commit()
    return len(files)


async def extract_events_workflow(
    session: "AsyncSession",
    dataset_id: str,
    batch_size: int = 50,
) -> int:
    """Parse a dataset's `.ics` files into events. Returns files processed.

    Only claims calendar files' rows: email / document rows of the same enrichment type
    belong to the LLM pass and stay pending for it.
    """
    calendar_files = await queue_event_extraction_enrichments(session=session, dataset_id=dataset_id)

    enrichment_repo = PostgresEnrichmentRepository(session=session)
    event_repo = PostgresEventRepository(session=session)
    location_repo = PostgresLocationRepository(session=session)

    total = calendar_files
    count = failed_count = event_count = 0

    with tqdm(total=total, desc="Extracting events", unit=" file") as pbar:
        while True:
            batch = await enrichment_repo.get_pending_batch(
                enrichment_type=EnrichmentType.EVENT_EXTRACTION,
                enrichable_type=EnrichableType.FILE,
                batch_size=batch_size,
                dataset_id=dataset_id,
                filetype_filter=_CALENDAR_FILETYPE,
            )
            if not batch:
                break

            await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
            await session.commit()

            completed, failed = [], {}
            for item in batch:
                try:
                    event_count += await _extract_calendar_file(
                        file_resource=item.resource, event_repo=event_repo, location_repo=location_repo
                    )
                    completed.append(item.enrichment.id)
                except Exception as e:
                    logger.error(f"Calendar extraction failed for file {item.resource['id']}: {e}")
                    await session.rollback()
                    failed[item.enrichment.id] = e

            if completed:
                await enrichment_repo.mark_completed_batch(completed)
            await enrichment_repo.mark_failed(failed)
            await session.commit()

            count += len(completed)
            failed_count += len(failed)
            pbar.set_postfix(failed=failed_count, events=event_count)
            pbar.update(len(completed) + len(failed))

    logger.success(f"Extracted {event_count} events from {count} calendar files ({failed_count} failed)")
    return count


async def get_event_extraction_stats(session: "AsyncSession", dataset_id: str | None = None) -> dict:
    """Enrichment stats for event extraction."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    return await enrichment_repo.get_enrichment_stats(
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.EVENT_EXTRACTION,
    )


# --------------------------------------------------------------------------- #
# LLM path: free-text event extraction over email / document bodies           #
# --------------------------------------------------------------------------- #
_PARTICIPANT_ROLES = {r.value for r in EventParticipantRole}
_PLACE_ROLES = {r.value for r in EventPlaceRole}


def _parse_iso(value: str | None, *, tz: str | None = None) -> datetime | None:
    """Best-effort ISO 8601 -> aware datetime (date-only allowed); None on failure.

    A naive result is localized to `tz` (an IANA name) when given, else to UTC.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(value.strip()[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        return parsed
    if tz:
        try:
            return parsed.replace(tzinfo=ZoneInfo(tz))
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return parsed.replace(tzinfo=UTC)


def _place_text(place) -> str:
    """Surface text of a place, whether it is an LLM `LlmEventPlace` or an `event_place` row."""
    return (getattr(place, "text", None) or getattr(place, "raw_text", None) or "").strip()


def _primary_place(places) -> str | None:
    """The place text to key dedup on: a `destination` if there is one, else the first non-empty."""
    ordered = sorted(places or [], key=lambda p: str(getattr(p, "role", "")).lower() != "destination")
    for place in ordered:
        text = _place_text(place)
        if text:
            return text
    return None


def _dedup_keys(
    *, title: str, date_start: datetime, event_type: EventType | str, place: str | None, uid: str | None
) -> set[str]:
    """The set of keys an event matches on. Two events collide if any key is shared."""
    day = date_start.date().isoformat()
    keys = {
        f"td:{normalize_name(title)}|{day}",
        f"tp:{event_type}|{day}|{normalize_name(place or title)}",
    }
    if uid:
        keys.add(f"uid:{uid.strip()}")
    return keys


def _llm_event_to_create(
    parsed: "ParsedEvent", *, dataset_id: str, file_id: str, model: str | None
) -> EventCreate | None:
    """Map one LLM `ParsedEvent` to an `EventCreate`; None when it has no usable start."""
    date_start = _parse_iso(parsed.date_start, tz=parsed.timezone)
    if date_start is None:
        return None
    return EventCreate(
        dataset_id=dataset_id,
        file_id=file_id,
        event_type=parsed.event_type,
        title=(parsed.title or "Untitled event")[:512],
        summary=parsed.summary,
        date_start=date_start,
        date_end=_parse_iso(parsed.date_end, tz=parsed.timezone),
        timezone=parsed.timezone,
        is_all_day=parsed.is_all_day,
        date_precision=parsed.date_precision,
        status=parsed.status,
        details=parsed.details,
        confidence=parsed.confidence,
        extractor=_LLM_EXTRACTOR,
        extraction_model=model,
    )


async def persist_llm_events(
    events: "list[ParsedEvent]",
    *,
    dataset_id: str,
    file_id: str,
    model: str | None,
    seen: set[str],
    event_repo: PostgresEventRepository,
) -> int:
    """Write one file's LLM `ParsedEvent`s as `event` (+ participant/place) rows.

    Skips an event whose dedup keys are already in `seen` (mutated in place).
    Returns events written. Shared by `extract_text_events_workflow` and the
    combined `extract_llm_workflow`.
    """
    written = 0
    for parsed in events:
        create = _llm_event_to_create(parsed, dataset_id=dataset_id, file_id=file_id, model=model)
        if create is None:
            continue
        keys = _dedup_keys(
            title=create.title,
            date_start=create.date_start,
            event_type=create.event_type,
            place=_primary_place(parsed.places),
            uid=None,
        )
        if keys & seen:
            continue
        seen |= keys

        event = await event_repo.add_event(create)
        for participant in parsed.participants:
            name = participant.name.strip()
            if not name:
                continue
            role = participant.role.strip().lower()
            await event_repo.add_participant(
                event_id=event.id,
                payload=EventParticipantCreate(
                    raw_name=name,
                    role=role if role in _PARTICIPANT_ROLES else EventParticipantRole.ATTENDEE,
                ),
            )
        for place in parsed.places:
            text = place.text.strip()
            if not text:
                continue
            role = place.role.strip().lower()
            await event_repo.add_place(
                event_id=event.id,
                payload=EventPlaceCreate(
                    raw_text=text,
                    role=role if role in _PLACE_ROLES else EventPlaceRole.VENUE,
                ),
            )
        written += 1
    return written


# --------------------------------------------------------------------------- #
# Gate: a cheap first pass deciding which files the LLM reads                 #
# --------------------------------------------------------------------------- #
EVENT_GATE_LABELS: dict[str, str] = {
    "personal_event": "booking confirmation, itinerary, reservation, or arranging to meet",
    "marketing": "marketing, promotion, or newsletter",
}
_GATE_POSITIVE_LABEL = "personal_event"
_GATE_MARKETING_LABEL = "marketing"
# Recall first: junk is cheap to mark invalid in bulk, a missed event is never seen.
DEFAULT_GATE_THRESHOLD = 0.4
DEFAULT_GATE_SAMPLE_RATE = 0.05
# The mail client's own classifier: its promotions tab and spam folder held none of the events the LLM
# found on a real mailbox, yet a third of what the GLiNER score passes. Skipped emails are still scored
# (and sampled), so what this costs stays measurable.
DEFAULT_GATE_SKIP_CATEGORIES = frozenset({EmailCategory.PROMOTIONS})
DEFAULT_GATE_SKIP_STATES = frozenset({EmailState.SPAM})
_GATE_MAX_CHARS = 20_000


def event_gate_score(label_scores: dict[str, float]) -> float:
    """Collapse the gate labels' scores into one "someone is taking part in something" score."""
    return label_scores.get(_GATE_POSITIVE_LABEL, 0.0)


def gate_rejects(
    score: float,
    metadata: dict | None,
    *,
    threshold: float,
    skip_categories: frozenset[EmailCategory] = DEFAULT_GATE_SKIP_CATEGORIES,
    skip_states: frozenset[EmailState] = DEFAULT_GATE_SKIP_STATES,
) -> bool:
    """Whether the gate keeps a text from the LLM: a low score, or a client category / state to skip."""
    if score < threshold:
        return True
    if not metadata or "email_client" not in metadata:
        return False
    if metadata.get("state") in skip_states:
        return True
    categories = metadata.get("categories") or EmailCategory.for_email(
        EmailClient(metadata["email_client"]), metadata.get("labels") or []
    )
    return bool(skip_categories.intersection(categories))


def _in_gate_sample(file_id: str, sample_rate: float) -> bool:
    """Whether a gate-rejected file is still read by the LLM (a stable slice, so re-runs agree)."""
    return int(hashlib.sha256(file_id.encode()).hexdigest()[:8], 16) < sample_rate * 0x1_0000_0000


async def gate_text_events_workflow(
    session: "AsyncSession",
    dataset_id: str,
    *,
    score_texts: Callable[[list[str]], list[float]],
    threshold: float = DEFAULT_GATE_THRESHOLD,
    sample_rate: float = DEFAULT_GATE_SAMPLE_RATE,
    filetype_groups: tuple[str, ...] = TEXT_EVENT_GROUPS_EMAIL,
    skip_categories: frozenset[EmailCategory] = DEFAULT_GATE_SKIP_CATEGORIES,
    skip_states: frozenset[EmailState] = DEFAULT_GATE_SKIP_STATES,
    batch_size: int = 64,
    model: str,
) -> int:
    """Score every pending, ungated text file and skip the ones unlikely to hold an event.

    Returns files skipped. `score_texts` maps texts to scores (0-1), stored as the
    file content's `tag_scores["event"]` and attributed to `model`. Files scoring under
    `threshold`, or emails the mail client filed under `skip_categories` / `skip_states`,
    are marked SKIPPED unless they fall in the `sample_rate` slice kept for measuring the
    gate. Pending files already scored (a copy of scored content, or a re-run with new
    settings) are re-decided from their stored score instead of being re-read.
    """
    rule = {"threshold": threshold, "skip_categories": skip_categories, "skip_states": skip_states}
    await queue_text_event_extraction_enrichments(
        session=session, dataset_id=dataset_id, filetype_groups=filetype_groups
    )
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    file_repo = PostgresFileRepository(session=session)
    pending = (
        select(
            EnrichmentTable.id,
            FileTable.id,
            func.left(ExtractedTextTable.content, _GATE_MAX_CHARS),
            ExtractedTextTable.metadata_,
        )
        .join(FileTable, EnrichmentTable.enrichable_id == FileTable.id)
        .join(ExtractedTextTable, ExtractedTextTable.file_id == FileTable.id)
        .where(
            EnrichmentTable.enrichable_type == EnrichableType.FILE,
            EnrichmentTable.enrichment_type == EnrichmentType.EVENT_EXTRACTION,
            EnrichmentTable.status == ProcessingStatus.PENDING,
            ~FileTable.tag_scores.has_key(EVENT_FILE_TAG),
            FileTable.dataset_id == dataset_id,
            FileTable.filetype_group.in_(filetype_groups),
            FileTable.mime_type != _CALENDAR_MIME,
        )
    )
    already_scored = (
        await session.execute(
            select(
                EnrichmentTable.id,
                FileTable.id,
                FileTable.tag_scores[EVENT_FILE_TAG].astext.cast(Float),
                ExtractedTextTable.metadata_,
            )
            .join(FileTable, EnrichmentTable.enrichable_id == FileTable.id)
            .outerjoin(ExtractedTextTable, ExtractedTextTable.file_id == FileTable.id)
            .where(
                EnrichmentTable.enrichable_type == EnrichableType.FILE,
                EnrichmentTable.enrichment_type == EnrichmentType.EVENT_EXTRACTION,
                EnrichmentTable.status == ProcessingStatus.PENDING,
                FileTable.tag_scores.has_key(EVENT_FILE_TAG),
                FileTable.dataset_id == dataset_id,
            )
        )
    ).all()
    copies = [
        e
        for e, file_id, score, metadata in already_scored
        if gate_rejects(score, metadata, **rule) and not _in_gate_sample(file_id, sample_rate)
    ]
    await enrichment_repo.mark_skipped_batch(copies)
    redecided = len(copies)
    skipped = 0

    total = (await session.execute(select(func.count()).select_from(pending.subquery()))).scalar_one()
    gated = 0

    with tqdm(total=total, desc="Gating events", unit=" file") as pbar:
        while rows := (await session.execute(pending.limit(batch_size))).all():
            scores = await asyncio.to_thread(score_texts, [content for _, _, content, _ in rows])
            await file_repo.set_tag_scores(
                tag=EVENT_FILE_TAG,
                scores={file_id: score for (_, file_id, _, _), score in zip(rows, scores, strict=True)},
                model=model,
            )
            rejected = [
                enrichment_id
                for (enrichment_id, file_id, _, metadata), score in zip(rows, scores, strict=True)
                if gate_rejects(score, metadata, **rule) and not _in_gate_sample(file_id, sample_rate)
            ]
            await enrichment_repo.mark_skipped_batch(rejected)
            await session.commit()

            gated += len(rows)
            skipped += len(rejected)
            pbar.set_postfix(skipped=skipped)
            pbar.update(len(rows))

    logger.success(
        f"Gated {gated} new text files: {gated - skipped} go to the LLM, {skipped} skipped; "
        f"{redecided} already-scored files skipped under the current gate settings"
    )
    return skipped + redecided


async def tag_event_files(
    session: "AsyncSession", *, with_events: list[str], without_events: list[str], model: str
) -> None:
    """Label files the LLM read: `event` positive when it found one, negative when it did not (as `model`)."""
    file_repo = PostgresFileRepository(session=session)
    for file_ids, label in ((with_events, ModelTagType.POSITIVE), (without_events, ModelTagType.NEGATIVE)):
        await file_repo.tag_files(file_ids=file_ids, tag=EVENT_FILE_TAG, label=label, source=TagSource.model(model))


async def get_event_gate_report(
    session: "AsyncSession",
    dataset_id: str,
    *,
    threshold: float,
    skip_categories: frozenset[EmailCategory] = DEFAULT_GATE_SKIP_CATEGORIES,
    skip_states: frozenset[EmailState] = DEFAULT_GATE_SKIP_STATES,
) -> dict:
    """How the gate did against the LLM: pass rate, and recall estimated from the sampled rejects."""
    rows = (
        await session.execute(
            select(
                FileTable.tag_scores[EVENT_FILE_TAG].astext.cast(Float),
                EnrichmentTable.status,
                FileTable.tags.has_key(EVENT_FILE_TAG),
                ExtractedTextTable.metadata_,
            )
            .join(FileTable, EnrichmentTable.enrichable_id == FileTable.id)
            .outerjoin(ExtractedTextTable, ExtractedTextTable.file_id == FileTable.id)
            .where(
                EnrichmentTable.enrichment_type == EnrichmentType.EVENT_EXTRACTION,
                EnrichmentTable.enrichable_type == EnrichableType.FILE,
                FileTable.tag_scores.has_key(EVENT_FILE_TAG),
                FileTable.dataset_id == dataset_id,
            )
        )
    ).all()
    report = dict.fromkeys(
        ("gated", "passed", "skipped", "passed_read", "passed_with_events", "rejected_read", "rejected_with_events"), 0
    )
    for score, status, has_event, metadata in rows:
        passed = not gate_rejects(
            score, metadata, threshold=threshold, skip_categories=skip_categories, skip_states=skip_states
        )
        read = status == ProcessingStatus.COMPLETED
        side = "passed" if passed else "rejected"
        report["gated"] += 1
        report["passed"] += passed
        report["skipped"] += status == ProcessingStatus.SKIPPED
        report[f"{side}_read"] += read
        report[f"{side}_with_events"] += bool(has_event)
    report |= {"threshold": threshold, "skip_categories": sorted(skip_categories), "skip_states": sorted(skip_states)}
    rejected = report["gated"] - report["passed"]
    if report["rejected_read"] and report["passed_read"]:
        missed = report["rejected_with_events"] / report["rejected_read"] * rejected
        found = report["passed_with_events"] / report["passed_read"] * report["passed"]
        report["estimated_recall"] = round(found / (found + missed), 3) if found + missed else None
    return report


def _reference_date(extracted) -> str | None:
    """ISO date the source was authored, to anchor relative dates in the LLM pass."""
    metadata = getattr(extracted, "metadata", None)
    if metadata is None:
        return None
    authored = getattr(metadata, "date_sent", None) or getattr(metadata, "date_content_created", None)
    return authored.date().isoformat() if authored is not None else None


async def _load_event_dedup_keys(session: "AsyncSession", dataset_id: str) -> set[str]:
    """Every dedup key for the dataset's existing events, so the LLM pass never re-adds one."""
    rows = (
        await session.execute(
            select(EventTable.id, EventTable.title, EventTable.date_start, EventTable.event_type, EventTable.uid).where(
                EventTable.dataset_id == dataset_id
            )
        )
    ).all()
    if not rows:
        return set()

    place_rows = (
        await session.execute(
            select(EventPlaceTable.event_id, EventPlaceTable.raw_text, EventPlaceTable.role).where(
                EventPlaceTable.event_id.in_([r.id for r in rows])
            )
        )
    ).all()
    places_by_event: dict[str, list] = {}
    for place in place_rows:
        places_by_event.setdefault(place.event_id, []).append(place)

    keys: set[str] = set()
    for row in rows:
        keys |= _dedup_keys(
            title=row.title,
            date_start=row.date_start,
            event_type=row.event_type,
            place=_primary_place(places_by_event.get(row.id, [])),
            uid=row.uid,
        )
    return keys


async def queue_text_event_extraction_enrichments(
    session: "AsyncSession", dataset_id: str, *, filetype_groups: "tuple[str, ...]" = TEXT_EVENT_GROUPS_EMAIL
) -> int:
    """Queue EVENT_EXTRACTION enrichments for a dataset's files in the given filetype groups."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    count = 0
    for group in filetype_groups:
        count += await enrichment_repo.queue_enrichments_by_filter(
            dataset_id=dataset_id,
            enrichment_type=EnrichmentType.EVENT_EXTRACTION,
            filetype_group=group,
        )
    await session.commit()
    return count


async def extract_text_events_workflow(
    session: "AsyncSession",
    dataset_id: str,
    batch_size: int = 20,
    model: str | None = None,
    filetype_groups: tuple[str, ...] = TEXT_EVENT_GROUPS_EMAIL,
    concurrency: int = 8,
) -> int:
    """Run `pyprompt` over a dataset's email (and optionally document) bodies into `event` rows.

    Returns files processed. Each file's text is anchored to its authored date so
    relative dates ("next Friday") resolve; events are deduped against every
    existing row in the dataset (`.ics` included). `concurrency` LLM calls are in
    flight at once so the server can batch them; writes stay serial. Each file
    read is tagged `event` positive or negative (see `tag_event_files`).
    """
    from pyprompt import PromptRunner, Settings

    await queue_text_event_extraction_enrichments(
        session=session, dataset_id=dataset_id, filetype_groups=filetype_groups
    )

    settings = Settings()
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)
    event_repo = PostgresEventRepository(session=session)
    runner = PromptRunner(settings)
    resolved_model = model or settings.llm.model
    seen = await _load_event_dedup_keys(session, dataset_id)
    semaphore = asyncio.Semaphore(concurrency)

    async def _call(item, extracted):
        async with semaphore:
            try:
                return item, await runner.extract_events(extracted.content, reference_date=_reference_date(extracted))
            except Exception as e:  # noqa: BLE001 -- reported per file below
                return item, e

    total = 0
    for group in filetype_groups:
        total += await enrichment_repo.count_pending(
            enrichment_type=EnrichmentType.EVENT_EXTRACTION,
            enrichable_type=EnrichableType.FILE,
            dataset_id=dataset_id,
            filetype_group_filter=group,
        )
    count = failed_count = event_count = 0
    attempted: set[str] = set()

    with tqdm(total=total, desc="Extracting events (llm)", unit=" file") as pbar:
        for group in filetype_groups:
            while True:
                batch = await enrichment_repo.get_pending_batch(
                    enrichment_type=EnrichmentType.EVENT_EXTRACTION,
                    enrichable_type=EnrichableType.FILE,
                    batch_size=batch_size,
                    dataset_id=dataset_id,
                    filetype_group_filter=group,
                )
                batch = [item for item in batch if item.enrichment.id not in attempted]
                if not batch:
                    break
                attempted.update(item.enrichment.id for item in batch)

                await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
                await session.commit()

                completed, failed, work = [], {}, []
                for item in batch:
                    extracted = (
                        await extracted_text_repo.get_by_file_id(item.resource["id"])
                        if item.resource.get("mime_type") != _CALENDAR_MIME
                        else None
                    )
                    if extracted is None or not (extracted.content or "").strip():
                        completed.append(item.enrichment.id)
                    else:
                        work.append((item, extracted))

                with_events, without_events = [], []
                for item, result in await asyncio.gather(*(_call(*w) for w in work)):
                    file_id = item.resource["id"]
                    if isinstance(result, Exception):
                        logger.error(f"LLM event extraction failed for file {file_id}: {result}")
                        failed[item.enrichment.id] = result
                        continue
                    try:
                        event_count += await persist_llm_events(
                            result.events,
                            dataset_id=item.resource["dataset_id"],
                            file_id=file_id,
                            model=resolved_model,
                            seen=seen,
                            event_repo=event_repo,
                        )
                        (with_events if result.events else without_events).append(file_id)
                        completed.append(item.enrichment.id)
                    except Exception as e:
                        logger.error(f"Persisting LLM events failed for file {file_id}: {e}")
                        await session.rollback()
                        failed[item.enrichment.id] = e

                await tag_event_files(
                    session, with_events=with_events, without_events=without_events, model=resolved_model
                )
                if completed:
                    await enrichment_repo.mark_completed_batch(completed)
                await enrichment_repo.mark_failed(failed)
                await session.commit()

                count += len(completed)
                failed_count += len(failed)
                pbar.set_postfix(failed=failed_count, events=event_count)
                pbar.update(len(completed) + len(failed))

                if failed and not completed:
                    logger.error(f"Every file in the batch failed ({len(failed)}); stopping. Check the LLM server.")
                    return count

    logger.success(f"Extracted {event_count} events from {count} text files ({failed_count} failed)")
    return count
