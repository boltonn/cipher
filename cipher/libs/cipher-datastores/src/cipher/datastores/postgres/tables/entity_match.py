from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, UniqueConstraint
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
    provisional_entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), nullable=True
    )

    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
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

    reviewed_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
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
    )
