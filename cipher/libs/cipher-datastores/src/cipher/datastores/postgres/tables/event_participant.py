from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.graph.event_participant import EventParticipantRole, RsvpStatus


class EventParticipantTable(Base):
    """A person/organisation attached to an event; `entity_id` is null until resolved."""

    __tablename__ = "event_participant"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str] = mapped_column(
        String, ForeignKey("event.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True, index=True
    )
    raw_name: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_email: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    role: Mapped[EventParticipantRole] = mapped_column(
        Enum(EventParticipantRole, native_enum=False),
        nullable=False,
        default=EventParticipantRole.ATTENDEE,
    )
    rsvp_status: Mapped[RsvpStatus | None] = mapped_column(Enum(RsvpStatus, native_enum=False), nullable=True)
    is_resource: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("ix_event_participant_entity", "entity_id"),)
