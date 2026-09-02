"""Calendar-event extraction workflow (EVENT_EXTRACTION enrichment).

Deterministic only: parses a dataset's `.ics` / `text/calendar` files
(`pyparse.parsers.calendar.ics`) into `event` rows. Each `VEVENT` becomes one
event (`extractor = "ics"`, `file_id` set) plus *unresolved*
`event_participant` rows (`raw_name` from ORGANIZER / ATTENDEE) and an
`event_place` row (`raw_text` from LOCATION). A later sweep resolves those to
entities / locations.

LLM extraction over free-text email bodies is intentionally **not** here -- it
belongs to a separate prompt-runner service, enabled later.

Re-runnable: a file with a completed EVENT_EXTRACTION row is skipped until
`reset-events` clears it.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresEventRepository,
)
from cipher.datastores.postgres.tables.enrichment import EnrichmentTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.schemas.graph.event import DatePrecision, EventCreate, EventStatus, EventType
from cipher.schemas.graph.event_participant import EventParticipantCreate, EventParticipantRole
from cipher.schemas.graph.event_place import EventPlaceCreate
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType, ProcessingStatus
from cipher.utils.io import fetch_bytes_from_uri

if TYPE_CHECKING:
    from pyparse.parsers.calendar.ics import ParsedCalendarEvent
    from sqlalchemy.ext.asyncio import AsyncSession

_EXTRACTOR = "ics"
_CALENDAR_MIME = "text/calendar"

_STATUS_MAP = {
    "CONFIRMED": EventStatus.CONFIRMED,
    "TENTATIVE": EventStatus.TENTATIVE,
    "CANCELLED": EventStatus.CANCELLED,
}

_TYPE_KEYWORDS: tuple[tuple[EventType, tuple[str, ...]], ...] = (
    (EventType.TRAVEL, ("flight", "train", "airline", "rail", "boarding", "rental car", "car rental")),
    (EventType.LODGING, ("hotel", "lodging", "check-in", "check in", "checkin", "airbnb", "stay")),
    (EventType.RESERVATION, ("reservation", "dinner", "lunch", "table", "booking")),
    (EventType.DELIVERY, ("delivery", "shipment", "package", "arriving")),
    (EventType.DEADLINE, ("due", "deadline", "payment", "renew")),
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
        extractor=_EXTRACTOR,
    )


async def _extract_calendar_file(
    file_resource: dict,
    event_repo: PostgresEventRepository,
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

        names = [(parsed.organizer, EventParticipantRole.ORGANIZER)] if parsed.organizer else []
        names += [(name, EventParticipantRole.ATTENDEE) for name in parsed.attendees]
        for name, role in names:
            if name and name.strip():
                await event_repo.add_participant(
                    event_id=event.id,
                    payload=EventParticipantCreate(raw_name=name.strip(), role=role),
                )
        if parsed.location and parsed.location.strip():
            await event_repo.add_place(event_id=event.id, payload=EventPlaceCreate(raw_text=parsed.location.strip()))
        written += 1
    return written


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
    """Parse a dataset's `.ics` files into events. Returns files processed."""
    await queue_event_extraction_enrichments(session=session, dataset_id=dataset_id)

    enrichment_repo = PostgresEnrichmentRepository(session=session)
    event_repo = PostgresEventRepository(session=session)

    total = await enrichment_repo.count_pending(
        enrichment_type=EnrichmentType.EVENT_EXTRACTION,
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
    )
    count = failed_count = event_count = 0

    with tqdm(total=total, desc="Extracting events", unit=" file") as pbar:
        while True:
            batch = await enrichment_repo.get_pending_batch(
                enrichment_type=EnrichmentType.EVENT_EXTRACTION,
                enrichable_type=EnrichableType.FILE,
                batch_size=batch_size,
                dataset_id=dataset_id,
            )
            if not batch:
                break

            await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
            await session.commit()

            completed, failed = [], []
            for item in batch:
                if item.resource.get("mime_type") != _CALENDAR_MIME:
                    completed.append(item.enrichment.id)
                    continue
                try:
                    event_count += await _extract_calendar_file(file_resource=item.resource, event_repo=event_repo)
                    completed.append(item.enrichment.id)
                except Exception as e:
                    logger.error(f"Calendar extraction failed for file {item.resource['id']}: {e}")
                    await session.rollback()
                    failed.append(item.enrichment.id)

            if completed:
                await enrichment_repo.mark_completed_batch(completed)
            if failed:
                await enrichment_repo.mark_failed_batch(failed, increment_retry=True)
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
