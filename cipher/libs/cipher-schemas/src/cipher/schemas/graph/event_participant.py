"""A person or organisation involved in an event.

`entity_id` points at a resolved `entity` (person/org) once entity resolution has
run; until then `raw_name` carries the surface text. Mirrors `event_place`.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from cipher.schemas._base.base import BaseModel


class EventParticipantRole(StrEnum):
    """How a participant stands to the event."""

    TRAVELER = "traveler"
    ATTENDEE = "attendee"
    ORGANIZER = "organizer"
    HOST = "host"
    GUEST = "guest"


class EventParticipantCreate(BaseModel):
    """Attach a participant to an event (the event id comes from the path)."""

    entity_id: str | None = Field(default=None, description="Resolved person/org entity; null while unresolved")
    raw_name: str | None = Field(default=None, description="Surface name when not resolved")
    role: EventParticipantRole = Field(default=EventParticipantRole.ATTENDEE)


class EventParticipant(EventParticipantCreate):
    """Participant row for API responses."""

    id: str
    event_id: str
    date_created: datetime

    model_config = {"from_attributes": True}
