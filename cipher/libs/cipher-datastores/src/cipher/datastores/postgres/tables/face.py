from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.identity.face import FACE_EMBEDDING_DIMENSION, FaceAssignmentMethod

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.face_match import FaceMatchTable
    from cipher.datastores.postgres.tables.image import ImageTable
    from cipher.datastores.postgres.tables.person import PersonTable


class FaceTable(Base):
    """Detected face table for Postgres."""

    __tablename__ = "face"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    image_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("image.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    person_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    bounding_box: Mapped[dict] = mapped_column(JSONB, nullable=False)
    landmarks: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)

    detector_model: Mapped[str | None] = mapped_column(String, nullable=True)
    detection_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pose: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(FACE_EMBEDDING_DIMENSION), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String, nullable=True)

    assignment_method: Mapped[FaceAssignmentMethod | None] = mapped_column(
        Enum(FaceAssignmentMethod, native_enum=False), nullable=True
    )
    assignment_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    is_representative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    image: Mapped["ImageTable"] = relationship(back_populates="faces", lazy="select")
    person: Mapped["PersonTable | None"] = relationship(back_populates="faces", lazy="select")
    match_candidates: Mapped[list["FaceMatchTable"]] = relationship(
        back_populates="face", cascade="all, delete-orphan", lazy="select"
    )

    __table_args__ = (
        Index(
            "hnsw_index_face_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_ip_ops"},
        ),
        Index("ix_face_image_person", "image_id", "person_id"),
        Index(
            "ix_face_representative_lookup",
            "person_id",
            "is_representative",
            postgresql_where=text("is_representative"),
        ),
        Index(
            "uq_face_primary_per_person",
            "person_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
        CheckConstraint(
            "NOT is_representative OR person_id IS NOT NULL",
            name="ck_face_representative_requires_person",
        ),
        CheckConstraint(
            "NOT is_primary OR is_representative",
            name="ck_face_primary_requires_representative",
        ),
    )
