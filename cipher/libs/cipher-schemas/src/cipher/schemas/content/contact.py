from datetime import datetime

from pydantic import Field

from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import PhoneNumber


class ContactBase(BaseModel):
    """Base contact schema."""

    address: str | None = Field(None, description="Address of the contact")
    date_of_birth: datetime | None = Field(None, description="Date of birth")
    emails: list[str] = Field(default_factory=list, description="Email addresses")
    first_name: str | None = Field(None, description="First name")
    full_name: str | None = Field(None, description="Full name")
    last_name: str | None = Field(None, description="Last name")
    note: str | None = Field(None, description="Additional notes")
    organization: str | None = Field(None, description="Organization")
    phone_numbers: list[PhoneNumber] = Field(default_factory=list, description="Phone numbers")
    date_created: datetime | None = Field(None, description="Creation timestamp")


class ContactCreate(ContactBase):
    """Contact creation schema."""

    file_id: str | None = None
    device_id: str | None = None


class ContactUpdate(BaseModel):
    """Contact update schema."""

    address: str | None = None
    date_of_birth: datetime | None = None
    emails: list[str] | None = None
    first_name: str | None = None
    full_name: str | None = None
    last_name: str | None = None
    note: str | None = None
    organization: str | None = None
    phone_numbers: list[PhoneNumber] | None = None
    file_id: str | None = None
    device_id: str | None = None


class Contact(ContactBase):
    """Contact model for API responses."""

    id: str
    file_id: str | None = None
    device_id: str | None = None

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "first_name": "John",
                "last_name": "Doe",
                "full_name": "John Doe",
                "emails": ["john.doe@example.com"],
                "phone_numbers": [{"number": "+1234567890", "type": "mobile"}],
                "organization": "Acme Corp",
                "address": "123 Main St",
                "date_of_birth": "1990-01-01T00:00:00Z",
                "date_created": "2024-01-01T12:00:00Z",
            }
        },
    }
