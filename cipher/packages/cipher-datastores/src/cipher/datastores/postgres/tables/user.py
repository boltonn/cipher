"""Database models - only imported by database layer."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cipher.datastores.postgres.tables.base import Base

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.dataset import DatasetTable


class UserDatasetAccessTable(Base):
    """Association table for user-dataset access."""

    __tablename__ = "user_dataset_access"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    dataset_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("dataset.id", ondelete="CASCADE"),
        primary_key=True,
    )


class UserTable(Base):
    """User table model for Postgres."""

    __tablename__ = "user"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    date_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Relationships
    datasets: Mapped[list["DatasetTable"]] = relationship(
        secondary="user_dataset_access",
        back_populates="users",
        lazy="select",
    )
