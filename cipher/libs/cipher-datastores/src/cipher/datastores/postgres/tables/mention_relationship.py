from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.graph.ontology import RelationshipType


class MentionRelationshipTable(Base):
    """A relation between two `mention` spans, asserted by an extractor before resolution.

    Endpoints are `mention` rows (not entities), so a relation survives while
    its spans are still unresolved. `resolve-entities` promotes a row into an
    `entity_relationship_candidate` once both endpoints carry an `entity_id`.
    """

    __tablename__ = "mention_relationship"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    dataset_id: Mapped[str] = mapped_column(
        String, ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False, index=True
    )
    src_mention_id: Mapped[str] = mapped_column(
        String, ForeignKey("mention.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dst_mention_id: Mapped[str] = mapped_column(
        String, ForeignKey("mention.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type: Mapped[RelationshipType] = mapped_column(
        Enum(RelationshipType, native_enum=False), nullable=False
    )
    directed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    file_id: Mapped[str | None] = mapped_column(String, ForeignKey("file.id", ondelete="SET NULL"), nullable=True)
    context: Mapped[str | None] = mapped_column(String, nullable=True)
    extractor: Mapped[str | None] = mapped_column(String, nullable=True)
    extraction_model: Mapped[str | None] = mapped_column(String, nullable=True)

    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint(
            "src_mention_id",
            "dst_mention_id",
            "relationship_type",
            name="uq_mention_relationship_triple",
        ),
    )
