from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.graph.entity_match import EntityMatchMethod, EntityMatchStatus


class EntityMatchTable(Base):
    """Candidate resolution of a mention (or provisional entity) to a canonical entity.

    The text-world analogue of `face_match`. Confirming attaches the mention
    to `entity_id` (and, if `provisional_entity_id` is set, merges that
    provisional entity into the canonical one).
    """

    __tablename__ = "entity_match"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    dataset_id: Mapped[str] = mapped_column(
        String, ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mention_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("mention.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Group-level rows (mention_id IS NULL): resolve every unresolved `name`
    # mention of this normalized value in one decision.
    normalized_value: Mapped[str | None] = mapped_column(String, nullable=True)
    mention_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provisional_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), nullable=True
    )

    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    decision_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    match_method: Mapped[EntityMatchMethod] = mapped_column(
        Enum(EntityMatchMethod, native_enum=False),
        nullable=False,
        default=EntityMatchMethod.SELECTOR_BLOCKING,
    )
    status: Mapped[EntityMatchStatus] = mapped_column(
        Enum(EntityMatchStatus, native_enum=False),
        nullable=False,
        default=EntityMatchStatus.PENDING,
        index=True,
    )

    reviewed_by: Mapped[str | None] = mapped_column(String, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String, nullable=True)

    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("mention_id", "entity_id", name="uq_entity_match_mention_entity"),
        Index(
            "ix_entity_match_pending",
            "dataset_id",
            "status",
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "uq_entity_match_name_group",
            "dataset_id",
            "normalized_value",
            "entity_id",
            unique=True,
            postgresql_where=text("mention_id IS NULL AND normalized_value IS NOT NULL"),
        ),
        # Entity->entity merge proposals: one row per (provisional entity, canonical
        # candidate). Confirming folds the provisional into `entity_id`.
        Index(
            "uq_entity_match_merge",
            "dataset_id",
            "provisional_entity_id",
            "entity_id",
            unique=True,
            postgresql_where=text("provisional_entity_id IS NOT NULL"),
        ),
    )
