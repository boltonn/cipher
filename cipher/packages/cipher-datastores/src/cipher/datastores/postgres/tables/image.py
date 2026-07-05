from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cipher.datastores.postgres.tables.base import Base

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.face import FaceTable
    from cipher.datastores.postgres.tables.file import FileTable

IMAGE_EMBEDDING_DIMENSION = 512


class ImageTable(Base):
    """Image metadata and embedding table."""

    __tablename__ = "image"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    file_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("file.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    width: Mapped[int] = mapped_column(nullable=False)
    height: Mapped[int] = mapped_column(nullable=False)

    camera_make: Mapped[str | None] = mapped_column(String, nullable=True)
    camera_model: Mapped[str | None] = mapped_column(String, nullable=True)
    focal_length: Mapped[float | None] = mapped_column(nullable=True)
    aperture: Mapped[float | None] = mapped_column(nullable=True)
    iso: Mapped[int | None] = mapped_column(nullable=True)

    date_taken: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    gps_altitude: Mapped[float | None] = mapped_column(nullable=True)

    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")

    embedding: Mapped[list[float] | None] = mapped_column(Vector(IMAGE_EMBEDDING_DIMENSION), nullable=True)

    embedding_model: Mapped[str | None] = mapped_column(String, nullable=True)

    file: Mapped["FileTable"] = relationship(back_populates="image", lazy="select")
    faces: Mapped[list["FaceTable"]] = relationship(back_populates="image", cascade="all, delete-orphan", lazy="select")

    __table_args__ = (
        Index(
            "hnsw_index_image_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_ip_ops"},
        ),
        Index(
            "ix_image_tags_gin",
            "tags",
            postgresql_using="gin",
        ),
    )
