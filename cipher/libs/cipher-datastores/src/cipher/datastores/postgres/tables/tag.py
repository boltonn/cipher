from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, Float, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas._base.common import ModelTagType
from cipher.schemas.interaction.tag import TagSourceType, TagTargetType


class TagTable(Base):
    """One source's decision about one tag on one target -- the source of truth for tags.

    `target_id` is polymorphic (a sha256 for content, else an entity / event id), so there
    is no FK; deletes of the target purge rows explicitly. The `tags` / `negative_tags` /
    `tag_scores` columns elsewhere are read copies rebuilt from here.
    """

    __tablename__ = "tag"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    target_type: Mapped[TagTargetType] = mapped_column(Enum(TagTargetType, native_enum=False), nullable=False)
    target_id: Mapped[str] = mapped_column(String, nullable=False)
    tag: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[ModelTagType | None] = mapped_column(Enum(ModelTagType, native_enum=False), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_type: Mapped[TagSourceType] = mapped_column(Enum(TagSourceType, native_enum=False), nullable=False)
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    date_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("target_type", "target_id", "tag", "source_type", "source_name", name="uq_tag"),
        Index("ix_tag_target", "target_type", "target_id"),
        # Predicted-tag filters ("scored >= x for tag t") are an index range scan.
        Index(
            "ix_tag_score",
            "target_type",
            "tag",
            "score",
            postgresql_where=text("score IS NOT NULL"),
        ),
    )
