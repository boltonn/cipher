"""Database models - only imported by database layer."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cipher.datastores.postgres.tables.base import Base

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.dataset import DatasetTable


class UserDatasetAccessTable(Base):
    """Dataset membership: a row means the user can see and work in that dataset.

    Owned by whatever grants access (an external entitlement sync, or an admin);
    admins (`user.is_admin`) see every dataset without rows here.
    """

    __tablename__ = "user_dataset_access"

    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    dataset_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("dataset.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    date_granted: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class UserTable(Base):
    """User table model for Postgres."""

    __tablename__ = "user"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    date_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    datasets: Mapped[list["DatasetTable"]] = relationship(
        secondary="user_dataset_access",
        back_populates="users",
        lazy="select",
    )
