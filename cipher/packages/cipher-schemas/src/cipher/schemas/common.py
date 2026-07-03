"""Common base schemas for the Cipher application."""

from enum import StrEnum
from typing import Any

from pydantic import Field, computed_field, field_validator

from cipher.schemas.base import BaseModel


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
