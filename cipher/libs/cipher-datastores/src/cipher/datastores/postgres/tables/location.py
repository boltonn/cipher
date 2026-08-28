from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.ontology import LocationSource


class LocationTable(Base):
    """Type-specific detail for an `entity` of type location (1:1 with `entity`)."""

    __tablename__ = "location"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    address_text: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geohash: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    source: Mapped[LocationSource] = mapped_column(
        Enum(LocationSource, native_enum=False), nullable=False, default=LocationSource.NAMED_MENTION
    )
    precision_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    admin_area: Mapped[str | None] = mapped_column(String, nullable=True)

    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    date_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
