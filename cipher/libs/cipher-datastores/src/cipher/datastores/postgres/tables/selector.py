from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.graph.ontology import SelectorKind


class SelectorTable(Base):
    """Type-specific detail for an `entity` of type selector (1:1 with `entity`).

    `(dataset_id, selector_kind, normalized_value)` is unique -- this is the
    blocking key used by entity resolution.
    """

    __tablename__ = "selector"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    dataset_id: Mapped[str] = mapped_column(
        String, ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False, index=True
    )

    selector_kind: Mapped[SelectorKind] = mapped_column(
        Enum(SelectorKind, native_enum=False), nullable=False
    )
    raw_value: Mapped[str] = mapped_column(String, nullable=False)
    normalized_value: Mapped[str] = mapped_column(String, nullable=False, index=True)
    region_hint: Mapped[str | None] = mapped_column(String, nullable=True)

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
        UniqueConstraint(
            "dataset_id", "selector_kind", "normalized_value", name="uq_selector_dataset_kind_value"
        ),
    )
