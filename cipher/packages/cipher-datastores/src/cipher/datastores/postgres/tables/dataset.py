from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cipher.datastores.postgres.tables.base import Base

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.file import FileTable
    from cipher.datastores.postgres.tables.user import UserTable


class DatasetTable(Base):
    """Dataset table model for Postgres."""

    __tablename__ = "dataset"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    description: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    date_last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    files: Mapped[list["FileTable"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )
    users: Mapped[list["UserTable"]] = relationship(
        secondary="user_dataset_access",
        back_populates="datasets",
    )
