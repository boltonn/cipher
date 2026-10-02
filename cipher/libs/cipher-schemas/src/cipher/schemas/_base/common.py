"""Common base schemas for the Cipher application."""

from enum import StrEnum
from typing import Any

from pydantic import Field, computed_field, field_validator

from cipher.schemas._base.base import BaseModel


class ModelDevice(StrEnum):
    """Model device enumeration."""

    CPU = "cpu"
    CUDA = "cuda"


class Sex(StrEnum):
    FEMALE = "female"
    MALE = "male"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class ModelTagType(StrEnum):
    """Tag type enumeration for an AI/ML model.

    Positive refers to a postive label.
    Negative refers to a hard negative or explicitly saying this object is not this tag.
    """

    NEGATIVE = "negative"
    POSITIVE = "positive"


class TagState(StrEnum):
    """Which of an object's tag stores a tag filter reads.

    `positive` / `negative` are the analyst's labels (`tags` / `negative_tags`);
    `predicted` is a tag a model scored (`tag_scores`) that has no label yet.
    """

    POSITIVE = "positive"
    NEGATIVE = "negative"
    PREDICTED = "predicted"


class PaginatedResponse(BaseModel):
    """Paginated records response schema."""

    total: int = Field(description="Total number of records available")
    page: int = Field(description="Current page number")
    limit: int = Field(description="Number of records per page")
    data: list[Any] = Field(description="List of records on the current page")

    @computed_field
    @property
    def has_more(self) -> bool:
        """Indicate if there are more pages available."""
        return self.page * self.limit < self.total


class PageParams(BaseModel):
    """Shared pagination + sort-direction fields for list/search parameter models.

    Subclasses add their own `limit` (bounds differ per resource) and a
    resource-specific `sort_by` enum. `offset` is derived from `page` and
    whatever `limit` the subclass declares.
    """

    page: int = Field(default=1, ge=1, description="1-based page number")
    sort_order: SortOrder = Field(default=SortOrder.DESC)

    @property
    def offset(self) -> int:
        """Row offset for the current page, given the subclass's `limit`."""
        return (self.page - 1) * getattr(self, "limit", 0)


class UriResponse(BaseModel):
    """URI response schema."""

    uri: str = Field(description="The URI of the resource")
    mime_type: str = Field(description="The MIME type of the resource")

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, v: str) -> str:
        """Validate that the URI is not empty."""
        return v.replace("file://", "") if v else v


class PhoneNumberType(StrEnum):
    """Phone number format type."""

    ITU_E164 = "ituE.164"
    RAW_PHONE_NUMBER = "rawPhoneNumber"


class PhoneNumber(BaseModel):
    value: str = Field(description="Normalized phone number string")
    type: PhoneNumberType
    label: str | None = None


class TranslationUpdate(BaseModel):
    translation: str = Field(..., min_length=1, description="The translated text content")


class TagRequest(BaseModel):
    tag: str = Field(..., min_length=1, example="political")
    type: ModelTagType = Field(
        ...,
        description="Whether to add to 'tags' (positive) or 'negative_tags' (negative)",
    )
