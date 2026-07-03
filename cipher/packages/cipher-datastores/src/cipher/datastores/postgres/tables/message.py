from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.common import PhoneNumberType
from cipher.schemas.message import MessageStatus

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.device import DeviceTable
    from cipher.datastores.postgres.tables.file import FileTable


class MessageTable(Base):
    """Message table model for Postgres."""

    __tablename__ = "message"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )

    message_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    file_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("file.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    sender: Mapped[str] = mapped_column(String, nullable=False, index=True)
    sender_type: Mapped[PhoneNumberType] = mapped_column(
        Enum(PhoneNumberType, native_enum=False), nullable=False
    )

    recipient: Mapped[str] = mapped_column(String, nullable=False, index=True)
    recipient_type: Mapped[PhoneNumberType] = mapped_column(
        Enum(PhoneNumberType, native_enum=False), nullable=False
    )

    date_sent: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    date_received: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    date_read: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    device_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("device.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    is_read: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    translation: Mapped[str | None] = mapped_column(Text, nullable=True)

    conversation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    message_status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus, native_enum=False), nullable=False
    )

    meaningful_hash: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )

    source_type: Mapped[str | None] = mapped_column(String, nullable=True)

    file: Mapped["FileTable | None"] = relationship(lazy="select")
    device: Mapped["DeviceTable"] = relationship(lazy="select")
