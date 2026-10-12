from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.graph.event import DatePrecision, EventSensitivity, EventStatus, EventType


class EventTable(Base):
    """A dated occurrence extracted from a document or parsed from a calendar file.

    Only the fields every event shares are columns; type-specific fields live in
    the `details` JSONB (a discriminated union keyed by `kind`). The people and
    places involved are rows in `event_participant` / `event_place`.
    """

    __tablename__ = "event"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    dataset_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("dataset.id", ondelete="CASCADE"), nullable=True, index=True
    )
    file_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("file.id", ondelete="SET NULL"), nullable=True, index=True
    )

    event_type: Mapped[EventType] = mapped_column(Enum(EventType, native_enum=False), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)

    date_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    date_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    is_all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    date_precision: Mapped[DatePrecision] = mapped_column(
        Enum(DatePrecision, native_enum=False), nullable=False, default=DatePrecision.EXACT
    )

    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, native_enum=False), nullable=False, default=EventStatus.CONFIRMED, index=True
    )
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    url: Mapped[str | None] = mapped_column(String, nullable=True)
    categories: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    sensitivity: Mapped[EventSensitivity | None] = mapped_column(
        Enum(EventSensitivity, native_enum=False), nullable=True
    )

    uid: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    recurrence_rule: Mapped[str | None] = mapped_column(String, nullable=True)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_created: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_last_modified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    extractor: Mapped[str | None] = mapped_column(String, nullable=True)
    extraction_model: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    date_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_event_dataset_start", "dataset_id", "date_start"),
        Index("ix_event_dataset_type", "dataset_id", "event_type"),
        Index("ix_event_title_trgm", "title", postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}),
    )
