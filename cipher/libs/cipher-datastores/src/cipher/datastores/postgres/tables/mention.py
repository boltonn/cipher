from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.graph.mention import MentionedType
from cipher.schemas.graph.ontology import EntityType, SelectorKind


class MentionTable(Base):
    """Evidence that some entity has a particular attribute value.

    Asserts `entity.<entity_attribute> = normalized_value` (surface form
    `surface_text`) for an entity of `entity_type`, anchored at one span.
    `mentioned_id` is a polymorphic pointer (no FK) to an `extracted_text`,
    `image`, `contact`, or `device` row, discriminated by `mentioned_type`
    (mirrors `comment.commentable_id`). `entity_id` is null until resolution --
    which may never happen (see `ontology.ResolutionPolicy`).
    """

    __tablename__ = "mention"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    dataset_id: Mapped[str] = mapped_column(
        String, ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True
    )

    mentioned_type: Mapped[MentionedType] = mapped_column(
        Enum(MentionedType, native_enum=False), nullable=False
    )
    mentioned_id: Mapped[str] = mapped_column(String, nullable=False)
    file_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )

    surface_text: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[EntityType | None] = mapped_column(
        Enum(EntityType, native_enum=False), nullable=True
    )
    entity_attribute: Mapped[str | None] = mapped_column(String, nullable=True)
    selector_kind: Mapped[SelectorKind | None] = mapped_column(
        Enum(SelectorKind, native_enum=False), nullable=True
    )
    normalized_value: Mapped[str | None] = mapped_column(String, nullable=True)

    start_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bounding_box: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    field_path: Mapped[str | None] = mapped_column(String, nullable=True)

    context: Mapped[str | None] = mapped_column(String, nullable=True)
    extractor: Mapped[str | None] = mapped_column(String, nullable=True)
    extraction_model: Mapped[str | None] = mapped_column(String, nullable=True)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

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
        Index("ix_mention_dataset_entity", "dataset_id", "entity_id"),
        Index("ix_mention_entity_attribute", "entity_id", "entity_attribute"),
        Index("ix_mention_file", "file_id"),
        Index("ix_mention_mentioned", "mentioned_type", "mentioned_id"),
        Index(
            "ix_mention_selector_value",
            "dataset_id",
            "normalized_value",
            postgresql_where=text("selector_kind IS NOT NULL"),
        ),
        Index(
            "ix_mention_unresolved",
            "dataset_id",
            postgresql_where=text("entity_id IS NULL"),
        ),
    )
