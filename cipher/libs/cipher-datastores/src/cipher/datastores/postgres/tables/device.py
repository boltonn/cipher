from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cipher.datastores.postgres.tables.base import Base

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.contact import ContactTable


class DeviceTable(Base):
    """Device table model for Postgres."""

    __tablename__ = "device"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    name: Mapped[str | None] = mapped_column(String, unique=True, nullable=True, index=True)
    serial_number: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    android_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String, nullable=True)
    brand: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    product_name: Mapped[str | None] = mapped_column(String, nullable=True)
    device_codename: Mapped[str | None] = mapped_column(String, nullable=True)

    phone_numbers: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)

    os_type: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[str | None] = mapped_column(String, nullable=True)
    sdk_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    build_id: Mapped[str | None] = mapped_column(String, nullable=True)
    build_fingerprint: Mapped[str | None] = mapped_column(String, nullable=True)
    build_date: Mapped[str | None] = mapped_column(String, nullable=True)
    carrier_name: Mapped[str | None] = mapped_column(String, nullable=True)
    carrier_code: Mapped[str | None] = mapped_column(String, nullable=True)
    sim_carrier: Mapped[str | None] = mapped_column(String, nullable=True)
    cpu_architecture: Mapped[str | None] = mapped_column(String, nullable=True)
    platform: Mapped[str | None] = mapped_column(String, nullable=True)

    imeis: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    date_first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_last_synced: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    additional_info: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    contacts: Mapped[list["ContactTable"]] = relationship(back_populates="device", lazy="select")
