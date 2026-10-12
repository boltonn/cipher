from datetime import UTC, datetime

from pydantic import Field, computed_field

from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import PageParams, PaginatedResponse


class UserBase(BaseModel):
    """Base user schema."""

    name: str = Field(max_length=255, description="User's full name")
    email: str = Field(max_length=255, description="User's email address")
    is_admin: bool = Field(default=False, description="Admins see every dataset and manage users and access")


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

    name: str | None = Field(default=None, max_length=255, description="User's full name")
    email: str | None = Field(default=None, max_length=255, description="User's email address")
    is_admin: bool | None = Field(default=None, description="Grant or remove admin")


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
                "isAdmin": False,
                "dateCreated": "2024-01-01T12:00:00Z",
                "dateUpdated": "2024-01-02T12:00:00Z",
            }
        },
    }


class UsersRequest(PageParams):
    """List users, optionally filtered by name or email."""

    query: str | None = Field(default=None, description="Case-insensitive match on name or email")
    limit: int = Field(default=25, ge=1, le=100)


class PaginatedUsersResponse(PaginatedResponse):
    """Paginated response for users."""

    data: list[User] = Field(description="Users on the current page")


class UserDatasetAccess(BaseModel):
    """One user's membership in one dataset."""

    user_id: str
    dataset_id: str
    date_granted: datetime


class UserDatasetsUpdate(BaseModel):
    """The complete set of datasets a user can access -- replaces whatever they had."""

    dataset_ids: list[str] = Field(default_factory=list, description="Dataset IDs the user is a member of")


class SelectedDatasetsUpdate(BaseModel):
    """The datasets the current user is working in -- replaces the previous selection."""

    dataset_ids: list[str] = Field(default_factory=list, description="Selected dataset IDs, in display order")
