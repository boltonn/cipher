from datetime import datetime

from pydantic import Field

from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import PhoneNumber


class DeviceBase(BaseModel):
    """Base device schema."""

    name: str | None = Field(None, description="Human-readable device name")
    serial_number: str | None = None
    android_id: str | None = None
    manufacturer: str | None = None
    brand: str | None = None
    model: str | None = None
    product_name: str | None = None
    device_codename: str | None = None
    phone_numbers: list[PhoneNumber] = Field(default_factory=list)
    os_type: str | None = None
    version: str | None = None
    sdk_version: int | None = None
    build_id: str | None = None
    build_fingerprint: str | None = None
    build_date: str | None = None
    carrier_name: str | None = None
    carrier_code: str | None = Field(None, description="MCC-MNC code")
    sim_carrier: str | None = None
    cpu_architecture: str | None = None
    platform: str | None = None
    imeis: list[str] = Field(default_factory=list)
    date_first_seen: datetime | None = None
    date_last_seen: datetime | None = None
    date_last_synced: datetime | None = None
    additional_info: dict = Field(default_factory=dict)


class DeviceCreate(DeviceBase):
    """Device creation schema."""

    pass


class DeviceUpdate(BaseModel):
    """Device update schema."""

    name: str | None = None
    serial_number: str | None = None
    android_id: str | None = None
    manufacturer: str | None = None
    brand: str | None = None
    model: str | None = None
    product_name: str | None = None
    device_codename: str | None = None
    phone_numbers: list[PhoneNumber] | None = None
    os_type: str | None = None
    version: str | None = None
    sdk_version: int | None = None
    build_id: str | None = None
    build_fingerprint: str | None = None
    build_date: str | None = None
    carrier_name: str | None = None
    carrier_code: str | None = None
    sim_carrier: str | None = None
    cpu_architecture: str | None = None
    platform: str | None = None
    imeis: list[str] | None = None
    date_first_seen: datetime | None = None
    date_last_seen: datetime | None = None
    date_last_synced: datetime | None = None
    additional_info: dict | None = None


class Device(DeviceBase):
    """Device model for API responses."""

    id: str

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "MYPHONE1",
                "serial_number": "ABCDEF123456",
                "android_id": "a1b2c3d4e5f6g7h8",
                "manufacturer": "Google",
                "brand": "Pixel",
                "model": "Pixel 5",
                "os_type": "Android",
                "version": "11",
                "sdk_version": 30,
                "carrier_name": "Example Carrier",
                "imeis": ["356789012345678", "356789012345686"],
            }
        },
    }
