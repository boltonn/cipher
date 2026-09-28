from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.graph.ontology import LocationSource


class LocationTable(Base):
    """A single geolocated point, from any source (mirrors shadowbot's `location`).

    Standalone: a row may hang off a source `file` (a photo's EXIF GPS), a
    resolved knowledge-graph entity (`entity.location_id` points here, sharing
    this row's id), both, or neither. `geom` is a generic GiST-indexed geometry;
    `latitude`/`longitude` are the denormalized representative point. Every row
    has coordinates -- an address with no fix stays an unresolved mention until
    it is geocoded. `(file_id, source)` is unique so a re-run of an extractor
    upserts rather than duplicates.
    """

    __tablename__ = "location"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    file_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("file.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dataset_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("dataset.id", ondelete="CASCADE"), nullable=True, index=True
    )

    geom: Mapped[Any] = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    altitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geohash: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    precision_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    bearing: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pitch: Mapped[float | None] = mapped_column(Float, nullable=True)
    velocity: Mapped[float | None] = mapped_column(Float, nullable=True)
    velocity_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    horizontal_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    vertical_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)

    name: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    admin_area: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    source: Mapped[LocationSource] = mapped_column(
        Enum(LocationSource, native_enum=False),
        nullable=False,
        default=LocationSource.NAMED_MENTION,
        index=True,
    )
    source_id: Mapped[str | None] = mapped_column(String, nullable=True)

    date_recorded: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
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
        # One point per (file, source) for single-fix sources (EXIF, device GPS);
        # `text_mention` is exempt -- a document can name many coordinates. The
        # column is a non-native Enum, so it stores the member *name*.
        Index(
            "uq_location_file_source",
            "file_id",
            "source",
            unique=True,
            postgresql_where=text("source <> 'TEXT_MENTION'"),
        ),
        Index("ix_location_geom", "geom", postgresql_using="gist"),
        Index("ix_location_source_source_id", "source", "source_id"),
    )
