from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.graph.ontology import SelectorSubtype, SelectorType


class SelectorTable(Base):
    """Type-specific detail for an `entity` of type selector (1:1 with `entity`).

    `normalized_value` + `selector_type` is the resolution blocking key. It is
    unique within a dataset for extracted selectors, and globally unique for
    analyst-attached selectors that carry no dataset (`dataset_id IS NULL` --
    external knowledge, like a person bridge node). `selector_subtype`
    (telegram, btc_address, ...) is descriptive and indexed for filtering.
    """

    __tablename__ = "selector"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    dataset_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("dataset.id", ondelete="CASCADE"), nullable=True, index=True
    )

    selector_type: Mapped[SelectorType] = mapped_column(
        Enum(SelectorType, native_enum=False, length=32), nullable=False
    )
    selector_subtype: Mapped[SelectorSubtype | None] = mapped_column(
        Enum(SelectorSubtype, native_enum=False, length=32), nullable=True, index=True
    )
    raw_value: Mapped[str] = mapped_column(String, nullable=False)
    normalized_value: Mapped[str] = mapped_column(String, nullable=False, index=True)
    region_hint: Mapped[str | None] = mapped_column(String, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

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
        Index(
            "uq_selector_dataset_type_value",
            "dataset_id",
            "selector_type",
            "normalized_value",
            unique=True,
            postgresql_where=text("dataset_id IS NOT NULL"),
        ),
        Index(
            "uq_selector_global_type_value",
            "selector_type",
            "normalized_value",
            unique=True,
            postgresql_where=text("dataset_id IS NULL"),
        ),
    )
