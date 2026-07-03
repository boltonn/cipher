from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cipher.datastores.postgres.tables.base import Base

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.device import DeviceTable
    from cipher.datastores.postgres.tables.file import FileTable


class ContactTable(Base):
    """Contact table model for Postgres."""

    __tablename__ = "contact"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )

    address: Mapped[str | None] = mapped_column(String, nullable=True)
    date_of_birth: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    emails: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    organization: Mapped[str | None] = mapped_column(String, nullable=True)
    phone_numbers: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    file_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("file.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    device_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("device.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    date_created: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    file: Mapped["FileTable | None"] = relationship(
        back_populates="contacts", lazy="select"
    )
    device: Mapped["DeviceTable | None"] = relationship(
        back_populates="contacts", lazy="select"
    )
