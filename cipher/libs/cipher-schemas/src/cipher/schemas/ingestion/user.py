from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, computed_field

if TYPE_CHECKING:
    from cipher.schemas.ingestion.dataset import Dataset


class UserBase(BaseModel):
    """Base user schema."""

    name: str = Field(max_length=255, description="User's full name")
    email: str = Field(max_length=255, description="User's email address")


class UserCreate(UserBase):
    """User creation schema."""

    @computed_field
    @property
    def date_created(self) -> datetime:
        """Automatically set the creation date to now."""
        return datetime.now(UTC)

    @computed_field
    @property
    def date_updated(self) -> datetime:
        """Automatically set the last updated date to now."""
        return datetime.now(UTC)


class UserUpdate(BaseModel):
    """User update schema."""

    name: str | None = Field(None, max_length=255, description="User's full name")
    email: str | None = Field(None, max_length=255, description="User's email address")

    @computed_field
    @property
    def date_updated(self) -> datetime:
        """Automatically set the last updated date to now."""
        return datetime.now(UTC)


class User(UserBase):
    """User model for API responses."""

    id: str
    date_created: datetime
    date_updated: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "John Doe",
                "email": "john.doe@example.com",
                "date_created": "2024-01-01T12:00:00Z",
                "date_updated": "2024-01-02T12:00:00Z",
            }
        },
    }


class UserDatasetAccess(BaseModel):
    """User dataset access - simplified."""

    user_id: str
    dataset_id: str

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "dataset_id": "123e4567-e89b-12d3-a456-426614174001",
            }
        },
    }


class UserWithDatasets(User):
    """User with their accessible datasets."""

    datasets: list["Dataset"] = Field(default_factory=list, description="Datasets user has access to")

    model_config = {
        "from_attributes": True,
    }
