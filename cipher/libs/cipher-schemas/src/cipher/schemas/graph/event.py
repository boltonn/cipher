"""Events: dated occurrences pulled from documents.

Travel, lodging, reservations, meetings, deadlines, deliveries.
An event is not a graph identity like a person or a place; it is a dated thing
that happened (or will happen), found by an LLM over extracted text or parsed
straight from a calendar (`.ics`) attachment. The table carries only the fields
every event shares; type-specific fields (a flight number, a booking reference,
an amount owed) live in the discriminated `details` payload. The people and
places involved are rows in `event_participant` / `event_place`, each pointing at
a resolved `entity` / `location` or just carrying surface text until resolution
runs.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, computed_field

from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import PageParams, PaginatedResponse
from cipher.schemas.graph.event_participant import EventParticipant
from cipher.schemas.graph.event_place import EventPlace


class EventType(StrEnum):
    """Coarse kind of an event; the calendar colours by category (see `EVENT_CATEGORY`)."""

    TRAVEL = "travel"
    LODGING = "lodging"
    RESERVATION = "reservation"
    MEETING = "meeting"
    DEADLINE = "deadline"
    DELIVERY = "delivery"
    OCCASION = "occasion"
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


class EventSortField(StrEnum):
    DATE_START = "date_start"
    DATE_CREATED = "date_created"
    DATE_UPDATED = "date_updated"


EVENT_CATEGORY: dict[EventType, str] = {
    EventType.TRAVEL: "travel",
    EventType.LODGING: "travel",
    EventType.RESERVATION: "personal",
    EventType.MEETING: "work",
    EventType.DEADLINE: "admin",
    EventType.DELIVERY: "logistics",
    EventType.OCCASION: "personal",
    EventType.OTHER: "other",
}

EVENT_TYPE_LABELS: dict[EventType, str] = {
    EventType.TRAVEL: "Travel",
    EventType.LODGING: "Lodging",
    EventType.RESERVATION: "Reservation",
    EventType.MEETING: "Meeting",
    EventType.DEADLINE: "Deadline",
    EventType.DELIVERY: "Delivery",
    EventType.OCCASION: "Occasion",
    EventType.OTHER: "Other",
}


def event_category(event_type: EventType) -> str:
    """Grouping key for calendar colour / filters."""
    return EVENT_CATEGORY.get(event_type, "other")


class TravelDetails(BaseModel):
    """Type-specific fields for `event_type == travel`."""

    kind: Literal["travel"] = "travel"
    mode: Literal["flight", "train", "bus", "ferry", "car_rental", "other"] | None = Field(default=None)
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


class DeadlineDetails(BaseModel):
    """Type-specific fields for `event_type == deadline`."""

    kind: Literal["deadline"] = "deadline"
    amount: float | None = Field(default=None, description="Amount due, if the source states one")
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    payee: str | None = Field(default=None)


class DeliveryDetails(BaseModel):
    """Type-specific fields for `event_type == delivery`."""

    kind: Literal["delivery"] = "delivery"
    carrier: str | None = Field(default=None)
    tracking_number: str | None = Field(default=None)
    order_number: str | None = Field(default=None)


EventDetails = Annotated[
    TravelDetails | LodgingDetails | ReservationDetails | DeadlineDetails | DeliveryDetails,
    Field(discriminator="kind"),
]


class EventBase(BaseModel):
    """Fields shared by every event."""

    dataset_id: str
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
    confidence: float | None = Field(default=None, ge=0, le=1)
    is_verified: bool | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
    notes: str | None = Field(default=None)


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

    dataset_id: str | None = Field(default=None)
    file_id: str | None = Field(default=None)
    query: str | None = Field(default=None, description="Substring match on title")
    event_type: EventType | None = Field(default=None)
    status: EventStatus | None = Field(default=None)
    participant_entity_id: str | None = Field(default=None, description="Events this entity takes part in")
    location_id: str | None = Field(default=None, description="Events attached to this place")
    date_from: datetime | None = Field(default=None, description="Keep events with date_start at/after this")
    date_to: datetime | None = Field(default=None, description="Keep events with date_start at/before this")
    is_verified: bool | None = Field(default=None)
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    limit: int = Field(default=25, ge=1, le=200)
    sort_by: EventSortField = Field(default=EventSortField.DATE_START)


class PaginatedEventsResponse(PaginatedResponse):
    """Paginated response for events."""

    data: list[Event] = Field(description="List of events")
