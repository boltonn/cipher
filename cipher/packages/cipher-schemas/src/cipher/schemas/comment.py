from datetime import datetime
from enum import StrEnum

from pydantic import Field

from cipher.schemas.base import BaseModel


class CommentableType(StrEnum):
    DATASET = "dataset"
    IMAGE = "image"


class CommentBase(BaseModel):
    """Base comment schema."""

    content: str = Field(max_length=5000, description="Comment content")
    commentable_type: CommentableType = Field(
        description="Type of resource being commented on"
    )
    commentable_id: str = Field(description="ID of the resource being commented on")


class CommentCreate(CommentBase):
    """Comment creation schema."""

    user_id: str


class CommentUpdate(BaseModel):
    """Comment update schema."""

    content: str | None = Field(None, max_length=5000)


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
