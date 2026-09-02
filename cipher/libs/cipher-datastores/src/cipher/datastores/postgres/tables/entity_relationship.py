from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.graph.ontology import RelationshipSource, RelationshipType


class EntityRelationshipTable(Base):
    """A confirmed typed edge between two entity nodes."""

    __tablename__ = "entity_relationship"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    # NULL when the edge spans datasets -- e.g. family_of between two person
    # bridge nodes, which are themselves dataset-agnostic.
    dataset_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("dataset.id", ondelete="CASCADE"), nullable=True, index=True
    )
    src_entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dst_entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type: Mapped[RelationshipType] = mapped_column(
        Enum(RelationshipType, native_enum=False), nullable=False
    )

    directed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[RelationshipSource] = mapped_column(
        Enum(RelationshipSource, native_enum=False), nullable=False, default=RelationshipSource.EXTRACTION
    )
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    date_observed_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_observed_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
        UniqueConstraint("src_entity_id", "dst_entity_id", "relationship_type", name="uq_entity_relationship_triple"),
        Index("ix_entity_relationship_src", "src_entity_id", "relationship_type"),
        Index("ix_entity_relationship_dst", "dst_entity_id", "relationship_type"),
    )
