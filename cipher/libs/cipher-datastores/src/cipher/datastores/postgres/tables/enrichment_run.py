from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base


class EnrichmentRunTable(Base):
    """One workflow invocation: what ran, over how many units, for how long.

    The calibration source for enrichment time estimates (median
    `duration_seconds / unit_count` per `enrichment_type` + `device`) and a
    plain audit log of what was run against a dataset and when. Written by the
    orchestration run recorder, never by the queue-level `enrichment` rows.

    A row with a `plan_id` is also a step of a run plan (docs/pipeline-runner.md):
    created `requested` / `queued`, claimed by a `cipher worker`, and kept alive by
    `date_heartbeat` while it runs.
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
    progress: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # per-step progress of a multi-step sweep

    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    date_started: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    date_completed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    plan_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    depends_on: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list, server_default="{}")
    pool: Mapped[str | None] = mapped_column(String, nullable=True)
    services: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list, server_default="{}")
    worker: Mapped[str | None] = mapped_column(String, nullable=True)
    process: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {host, worker_pid, pid, log}
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    code_version: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {"approved": {...}, "ran": {...}}
    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), server_default=text("now()")
    )
    date_approved: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_enrichment_run_type_device_status", "enrichment_type", "device", "status"),
        Index("ix_enrichment_run_waiting", "pool", "date_created", postgresql_where=text("status = 'queued'")),
    )
