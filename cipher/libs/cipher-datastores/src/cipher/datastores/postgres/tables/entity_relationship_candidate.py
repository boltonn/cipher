from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.graph.entity_relationship import RelationshipCandidateMethod, RelationshipCandidateStatus
from cipher.schemas.graph.ontology import RelationshipType


class EntityRelationshipCandidateTable(Base):
    """A proposed typed edge awaiting (or having received) analyst review."""

    __tablename__ = "entity_relationship_candidate"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    dataset_id: Mapped[str] = mapped_column(
        String, ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False, index=True
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

    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[RelationshipCandidateMethod] = mapped_column(
        Enum(RelationshipCandidateMethod, native_enum=False),
        nullable=False,
        default=RelationshipCandidateMethod.CO_MENTION,
    )
    status: Mapped[RelationshipCandidateStatus] = mapped_column(
        Enum(RelationshipCandidateStatus, native_enum=False),
        nullable=False,
        default=RelationshipCandidateStatus.PENDING,
        index=True,
    )
    evidence_mention_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("mention.id", ondelete="SET NULL"), nullable=True
    )

    reviewed_by: Mapped[str | None] = mapped_column(String, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String, nullable=True)

    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint(
            "src_entity_id", "dst_entity_id", "relationship_type", name="uq_entity_relationship_candidate_triple"
        ),
        Index(
            "ix_entity_relationship_candidate_pending",
            "dataset_id",
            "status",
            postgresql_where=text("status = 'pending'"),
        ),
    )
