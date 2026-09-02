from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.graph.event_place import EventPlaceRole


class EventPlaceTable(Base):
    """A place attached to an event (venue / origin / destination); `location_id` null until geocoded."""

    __tablename__ = "event_place"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str] = mapped_column(
        String, ForeignKey("event.id", ondelete="CASCADE"), nullable=False, index=True
    )
    location_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("location.id", ondelete="SET NULL"), nullable=True, index=True
    )
    raw_text: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[EventPlaceRole] = mapped_column(
        Enum(EventPlaceRole, native_enum=False), nullable=False, default=EventPlaceRole.VENUE
    )
    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("ix_event_place_location", "location_id"),)
