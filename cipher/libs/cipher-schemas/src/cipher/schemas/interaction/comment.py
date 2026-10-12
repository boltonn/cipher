from datetime import UTC, datetime

from pydantic import Field, computed_field

from cipher.schemas._base.base import BaseModel, StrEnum


class CommentableType(StrEnum):
    """What a comment is on.

    `entity` covers every entity type (person, organization, location, selector, ...); person
    and location records share their entity's id, so a person has one thread, not two.
    """

    DATASET = "dataset"
    IMAGE = "image"
    FILE = "file"
    ENTITY = "entity"


class CommentBase(BaseModel):
    """Base comment schema."""

    content: str = Field(max_length=5000, description="Comment content")
    commentable_type: CommentableType = Field(description="Type of resource being commented on")
    commentable_id: str = Field(description="ID of the resource being commented on")


class CommentCreate(CommentBase):
    """Comment creation schema."""

    user_id: str


class CommentUpdate(BaseModel):
    """Comment update schema."""

    content: str | None = Field(None, max_length=5000)

    @computed_field
    @property
    def date_updated(self) -> datetime:
        """Automatically set the last updated date to now."""
        return datetime.now(UTC)


class Comment(CommentBase):
    """Comment model for API responses."""

    id: str
    user_id: str
    date_created: datetime
    date_updated: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "content": "This is a great dataset!",
                "commentable_type": "dataset",
                "commentable_id": "123e4567-e89b-12d3-a456-426614174001",
                "user_id": "123e4567-e89b-12d3-a456-426614174002",
                "date_created": "2024-01-01T12:00:00Z",
                "date_updated": "2024-01-01T12:00:00Z",
            }
        },
    }


class CommentPublic(Comment):
    """Comment model with the author's display name denormalized in."""

    user_name: str = Field(description="Display name of the comment's author")
