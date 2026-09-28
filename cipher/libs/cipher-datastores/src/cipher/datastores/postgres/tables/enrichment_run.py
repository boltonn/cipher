from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base


class EnrichmentRunTable(Base):
    """One workflow invocation: what ran, over how many units, for how long.

    The calibration source for enrichment time estimates (median
    `duration_seconds / unit_count` per `enrichment_type` + `device`) and a
    plain audit log of what was run against a dataset and when. Written by the
    orchestration run recorder, never by the queue-level `enrichment` rows.
    """

    __tablename__ = "enrichment_run"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    enrichment_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    dataset_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("dataset.id", ondelete="SET NULL"), nullable=True, index=True
    )

    device: Mapped[str] = mapped_column(String, nullable=False, default="na")
    unit: Mapped[str] = mapped_column(String, nullable=False, default="file")
    unit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    date_started: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    date_completed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("ix_enrichment_run_type_device_status", "enrichment_type", "device", "status"),
    )
