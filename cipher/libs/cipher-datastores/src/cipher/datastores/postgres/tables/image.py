from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cipher.datastores.postgres.tables.base import Base

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.face import FaceTable

IMAGE_EMBEDDING_DIMENSION = 512


class ImageTable(Base):
    """Image content table, keyed by sha256.

    Identical image bytes -- however many `File` rows reference them (same content
    ingested at different paths, or found in different datasets) -- are only ever
    embedded/stored once. Occurrence-specific data (which file(s), which dataset) lives
    on `FileTable` and is resolved via `File.sha256 == Image.id`, not a foreign key here.
    """

    __tablename__ = "image"

    id: Mapped[str] = mapped_column(String, primary_key=True, doc="sha256 of the image content")

    width: Mapped[int] = mapped_column(nullable=False)
    height: Mapped[int] = mapped_column(nullable=False)

    camera_make: Mapped[str | None] = mapped_column(String, nullable=True)
    camera_model: Mapped[str | None] = mapped_column(String, nullable=True)
    focal_length: Mapped[float | None] = mapped_column(nullable=True)
    aperture: Mapped[float | None] = mapped_column(nullable=True)
    iso: Mapped[int | None] = mapped_column(nullable=True)

    date_taken: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    gps_latitude: Mapped[float | None] = mapped_column(nullable=True)
    gps_longitude: Mapped[float | None] = mapped_column(nullable=True)
    gps_altitude: Mapped[float | None] = mapped_column(nullable=True)

    # Labels for training classifiers over this image's embedding: `tags` says "is this",
    # `negative_tags` says "is explicitly not this" (a hard negative). A tag is in at most one.
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    negative_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # A model's confidence that a tag applies ({tag: 0-1}) -- a prediction, kept apart from the labels above.
    tag_scores: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    embedding: Mapped[list[float] | None] = mapped_column(Vector(IMAGE_EMBEDDING_DIMENSION), nullable=True)

    embedding_model: Mapped[str | None] = mapped_column(String, nullable=True)

    faces: Mapped[list["FaceTable"]] = relationship(back_populates="image", cascade="all, delete-orphan", lazy="select")

    __table_args__ = (
        Index(
            "hnsw_index_image_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_ip_ops"},
        ),
        Index("ix_image_tags_gin", "tags", postgresql_using="gin"),
        Index("ix_image_negative_tags_gin", "negative_tags", postgresql_using="gin"),
    )
