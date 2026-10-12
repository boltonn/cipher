"""Events: dated occurrences pulled from documents.

Travel, lodging, reservations, meetings, gatherings, deliveries.
An event is not a graph identity like a person or a place; it is a dated thing
that happened (or will happen), found by an LLM over extracted text or parsed
straight from a calendar (`.ics`) attachment. The table carries only the fields
every event shares; type-specific fields (a flight number, a booking reference,
a tracking number) live in the discriminated `details` payload. The people and
places involved are rows in `event_participant` / `event_place`, each pointing at
a resolved `entity` / `location` or just carrying surface text until resolution
runs.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, computed_field

from cipher.schemas._base.base import BaseModel, StrEnum
from cipher.schemas._base.common import PageParams, PaginatedResponse
from cipher.schemas.graph.event_participant import EventParticipant
from cipher.schemas.graph.event_place import EventPlace
from cipher.schemas.graph.ontology import EntityType

# `file.tags` / `file.negative_tags` label: the file does / does not describe an event someone takes part in.
EVENT_FILE_TAG = "event"


class EventType(StrEnum):
    """Coarse kind of an event; the calendar colours by category (see `EVENT_CATEGORY`).

    `MEETING` is named people getting together (call, sync, interview, appointment);
    `GATHERING` is an organized event many people attend (conference, wedding, party, ceremony).
    """

    TRAVEL = "travel"
    LODGING = "lodging"
    RESERVATION = "reservation"
    MEETING = "meeting"
    GATHERING = "gathering"
    DELIVERY = "delivery"
    OTHER = "other"


class EventStatus(StrEnum):
    """Lifecycle of an event as stated by its source."""

    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class DatePrecision(StrEnum):
    """How exact `date_start` is -- LLM-extracted dates are often fuzzy."""

    EXACT = "exact"
    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    APPROXIMATE = "approximate"


class EventSensitivity(StrEnum):
    """Visibility class carried by a source calendar entry (iCalendar `CLASS`)."""

    PUBLIC = "public"
    PRIVATE = "private"
    CONFIDENTIAL = "confidential"


class EventSortField(StrEnum):
    DATE_START = "date_start"
    DATE_CREATED = "date_created"
    DATE_UPDATED = "date_updated"
    TITLE = "title"
    EVENT_TYPE = "event_type"
    STATUS = "status"


EVENT_CATEGORY: dict[EventType, str] = {
    EventType.TRAVEL: "travel",
    EventType.LODGING: "travel",
    EventType.RESERVATION: "personal",
    EventType.MEETING: "work",
    EventType.GATHERING: "personal",
    EventType.DELIVERY: "logistics",
    EventType.OTHER: "other",
}

EVENT_TYPE_LABELS: dict[EventType, str] = {
    EventType.TRAVEL: "Travel",
    EventType.LODGING: "Lodging",
    EventType.RESERVATION: "Reservation",
    EventType.MEETING: "Meeting",
    EventType.GATHERING: "Gathering",
    EventType.DELIVERY: "Delivery",
    EventType.OTHER: "Other",
}


def event_category(event_type: EventType) -> str:
    """Grouping key for calendar colour / filters."""
    return EVENT_CATEGORY.get(event_type, "other")


class TravelMode(StrEnum):
    FLIGHT = "flight"
    TRAIN = "train"
    BUS = "bus"
    FERRY = "ferry"
    CAR_RENTAL = "car_rental"
    OTHER = "other"


class TravelDetails(BaseModel):
    """Type-specific fields for `event_type == travel`."""

    kind: Literal["travel"] = "travel"
    mode: TravelMode | None = Field(default=None)
    operator: str | None = Field(default=None, description="Carrier or rental company")
    number: str | None = Field(default=None, description="Flight / train / booking number")
    confirmation: str | None = Field(default=None, description="Confirmation code or record locator")


class LodgingDetails(BaseModel):
    """Type-specific fields for `event_type == lodging`."""

    kind: Literal["lodging"] = "lodging"
    operator: str | None = Field(default=None, description="Hotel, host, or booking platform")
    confirmation: str | None = Field(default=None)
    nights: int | None = Field(default=None, ge=0)
    guests: int | None = Field(default=None, ge=0)


class ReservationDetails(BaseModel):
    """Type-specific fields for `event_type == reservation`."""

    kind: Literal["reservation"] = "reservation"
    operator: str | None = Field(default=None, description="Restaurant or provider")
    confirmation: str | None = Field(default=None)
    party_size: int | None = Field(default=None, ge=0)


class DeliveryDetails(BaseModel):
    """Type-specific fields for `event_type == delivery`."""

    kind: Literal["delivery"] = "delivery"
    carrier: str | None = Field(default=None)
    tracking_number: str | None = Field(default=None)
    order_number: str | None = Field(default=None)


EventDetails = Annotated[
    TravelDetails | LodgingDetails | ReservationDetails | DeliveryDetails,
    Field(discriminator="kind"),
]


class EventBase(BaseModel):
    """Fields shared by every event."""

    dataset_id: str | None = Field(
        default=None,
        description="Ingest the event was found in; null for an analyst-authored or cross-dataset event. "
        "`file_id` is the real provenance link.",
    )
    file_id: str | None = Field(default=None, description="Source file the event was extracted from")

    event_type: EventType
    title: str = Field(max_length=512, description="Short human-readable label")
    summary: str | None = Field(default=None, description="Longer description when the source gives one")

    date_start: datetime = Field(description="Start; local wall time, zone in `timezone`")
    date_end: datetime | None = Field(default=None, description="End; None for a point-in-time event")
    timezone: str | None = Field(default=None, description="IANA tz name for the local wall time")
    is_all_day: bool = Field(default=False)
    date_precision: DatePrecision = Field(default=DatePrecision.EXACT)

    status: EventStatus = Field(default=EventStatus.CONFIRMED)
    details: EventDetails | None = Field(default=None, description="Type-specific fields, discriminated on `kind`")

    url: str | None = Field(default=None, description="Booking / meeting link (iCalendar `URL`)")
    categories: list[str] = Field(
        default_factory=list, description="Raw source labels (iCalendar `CATEGORIES`); distinct from analyst `tags`"
    )
    sensitivity: EventSensitivity | None = Field(
        default=None, description="Source visibility class (iCalendar `CLASS`)"
    )

    uid: str | None = Field(
        default=None, description="Stable source identifier (iCalendar `UID`); identity key across updates"
    )
    recurrence_rule: str | None = Field(
        default=None, description="Raw iCalendar `RRULE`; stored verbatim, not expanded into instances"
    )
    sequence: int | None = Field(
        default=None, description="Source revision number (iCalendar `SEQUENCE`); higher supersedes for the same `uid`"
    )
    source_created: datetime | None = Field(
        default=None, description="When the source entry was created (iCalendar `CREATED` / `DTSTAMP`)"
    )
    source_last_modified: datetime | None = Field(
        default=None, description="When the source entry was last changed (iCalendar `LAST-MODIFIED`)"
    )

    extractor: str | None = Field(default=None, description="What produced the row: 'ics', 'llm', 'manual'")
    extraction_model: str | None = Field(default=None, description="Model id/version when extractor is an LLM")
    confidence: float | None = Field(default=None, ge=0, le=1, description="Extraction confidence")
    is_verified: bool = Field(default=False, description="An analyst has confirmed this event")
    tags: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None)


class EventCreate(EventBase):
    """Create payload. Participants and places are attached via their own endpoints."""


class EventUpdate(BaseModel):
    """Partial update for an existing event."""

    event_type: EventType | None = Field(default=None)
    title: str | None = Field(default=None, max_length=512)
    summary: str | None = Field(default=None)
    date_start: datetime | None = Field(default=None)
    date_end: datetime | None = Field(default=None)
    timezone: str | None = Field(default=None)
    is_all_day: bool | None = Field(default=None)
    date_precision: DatePrecision | None = Field(default=None)
    status: EventStatus | None = Field(default=None)
    details: EventDetails | None = Field(default=None)
    url: str | None = Field(default=None)
    categories: list[str] | None = Field(default=None)
    sensitivity: EventSensitivity | None = Field(default=None)
    confidence: float | None = Field(default=None, ge=0, le=1)
    is_verified: bool | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
    notes: str | None = Field(default=None)


class EventIdsRequest(BaseModel):
    """A set of events to act on together (e.g. mark invalid)."""

    event_ids: list[str] = Field(min_length=1)


class Event(EventBase):
    """Event model for API responses (list rows / calendar cells)."""

    id: str
    date_created: datetime
    date_updated: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def category(self) -> str:
        """Grouping key derived from `event_type` (see `EVENT_CATEGORY`)."""
        return event_category(self.event_type)


class EventWithLinks(Event):
    """A single event plus the people and places attached to it."""

    participants: list[EventParticipant] = Field(default_factory=list)
    places: list[EventPlace] = Field(default_factory=list)


class EventSearchParameters(PageParams):
    """Filter surface for the events table."""

    dataset_ids: list[str] | None = Field(default=None, description="Events from any of these datasets")
    file_id: str | None = Field(default=None)
    query: str | None = Field(default=None, description="Substring match on title")
    event_type: EventType | None = Field(default=None)
    category: str | None = Field(default=None, description="Match a raw source label (iCalendar `CATEGORIES`)")
    uid: str | None = Field(default=None, description="Exact match on the source identifier")
    status: EventStatus | None = Field(default=None)
    participant_entity_ids: list[str] | None = Field(
        default=None, description="Events any of these entities take part in (OR with participant_names)"
    )
    participant_names: list[str] | None = Field(
        default=None, description="Substring match on a participant's raw name/email or linked entity name"
    )
    location_ids: list[str] | None = Field(
        default=None, description="Events attached to any of these locations (OR with place_names)"
    )
    place_names: list[str] | None = Field(
        default=None, description="Substring match on a place's raw text or linked location name"
    )
    date_from: datetime | None = Field(default=None, description="Keep events with date_start at/after this")
    date_to: datetime | None = Field(default=None, description="Keep events with date_start at/before this")
    is_verified: bool | None = Field(default=None)
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    limit: int = Field(default=25, ge=1, le=200)
    sort_by: EventSortField = Field(default=EventSortField.DATE_START)


class PaginatedEventsResponse(PaginatedResponse):
    """Paginated response for events."""

    data: list[Event] = Field(description="List of events")


class EventParticipantOption(BaseModel):
    """A participant on events: a linked entity, or raw text not yet resolved (`entity_id` null)."""

    entity_id: str | None = Field(default=None)
    person_id: str | None = Field(default=None, description="Bridged person, for a face thumbnail")
    name: str
    entity_type: EntityType | None = Field(default=None)
    is_provisional: bool = Field(default=False, description="Linked entity was auto-created, not yet confirmed")
    event_count: int


class EventPlaceOption(BaseModel):
    """A place on events: a linked location, or raw text not yet geocoded (`location_id` null)."""

    location_id: str | None = Field(default=None)
    name: str
    event_count: int


class EventMonthCount(BaseModel):
    """How many events start in one calendar month -- drives calendar month/year navigation."""

    month: str = Field(description="Month as YYYY-MM")
    count: int = Field(description="Events whose date_start falls in the month")
