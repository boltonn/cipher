from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.enrichment import EnrichableType, EnrichmentType, ProcessingStatus


class EnrichmentTable(Base):
    """Polymorphic enrichment tracking table."""

    __tablename__ = "enrichment"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid4())
    )

    enrichable_type: Mapped[EnrichableType] = mapped_column(
        Enum(EnrichableType, native_enum=False), nullable=False, index=True
    )
    enrichable_id: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )

    enrichment_type: Mapped[EnrichmentType] = mapped_column(
        Enum(EnrichmentType, native_enum=False), nullable=False, index=True
    )

    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, native_enum=False),
        nullable=False,
        default=ProcessingStatus.PENDING,
        index=True,
    )

    date_started: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    date_completed: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

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
        Index(
            "idx_enrichment_resource_type_unique",
            "enrichable_type",
            "enrichable_id",
            "enrichment_type",
            unique=True,
        ),
        Index(
            "idx_enrichment_pending",
            "enrichment_type",
            "enrichable_type",
            "date_created",
            postgresql_where=text("status IN ('pending', 'failed')"),
        ),
        Index(
            "idx_enrichment_type_status_retry",
            "enrichment_type",
            "status",
            "retry_count",
        ),
        Index("idx_enrichment_polymorphic", "enrichable_type", "enrichable_id"),
    )
