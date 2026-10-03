from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base


class OrganizationTable(Base):
    """Type-specific detail for an `entity` of type organization (1:1 with `entity`)."""

    __tablename__ = "organization"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    legal_name: Mapped[str | None] = mapped_column(String, nullable=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Same free-text vocabulary style as `location.category` ('company', 'agency', 'office', ...).
    category: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # The organization this one is a unit of (division, office, branch). Mirrored as a
    # `part_of` edge so the hierarchy shows in the graph.
    parent_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True, index=True
    )
    country: Mapped[str | None] = mapped_column(String, nullable=True)

    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    date_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
