from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base


class TableMappingTable(Base):
    """How a tabular layout's columns map onto the ontology (`TableMapping`), shared per dataset + header layout.

    Files point at it through `file.table_sheets[].fingerprint`. `sample` holds a
    few hundred data rows so edits are re-evaluated without the file. Review state
    is `is_verified` + who, like entities. See docs/tabular-mapping.md.
    """

    __tablename__ = "table_mapping"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(String, ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String, nullable=False)
    mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sample: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_by: Mapped[str | None] = mapped_column(String, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    date_verified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    date_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (UniqueConstraint("dataset_id", "fingerprint", name="uq_table_mapping_dataset_fingerprint"),)
