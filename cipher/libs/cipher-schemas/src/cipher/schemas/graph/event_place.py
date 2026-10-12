"""A place involved in an event: its venue, or the origin/destination of travel.

`location_id` points at a resolved `location` row once it is geocoded; until then
`raw_text` carries the surface place text. Mirrors `event_participant`.
"""

from datetime import datetime

from pydantic import Field

from cipher.schemas._base.base import BaseModel, StrEnum


class EventPlaceRole(StrEnum):
    """What part the place plays in the event."""

    VENUE = "venue"
    ORIGIN = "origin"
    DESTINATION = "destination"


class EventPlaceCreate(BaseModel):
    """Attach a place to an event (the event id comes from the path)."""

    location_id: str | None = Field(default=None, description="Resolved location row; null until geocoded")
    raw_text: str | None = Field(default=None, description="Surface place text when not geocoded")
    role: EventPlaceRole = Field(default=EventPlaceRole.VENUE)


class EventPlace(EventPlaceCreate):
    """Place row for API responses."""

    id: str
    event_id: str
    date_created: datetime

    model_config = {"from_attributes": True}
