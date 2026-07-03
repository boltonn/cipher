from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import Field, computed_field, model_validator
from pydantic.alias_generators import to_snake

from cipher.schemas.base import BaseModel
from cipher.schemas.common import PaginatedResponse, SortOrder


class DatasetSortField(StrEnum):
    NAME = "name"
    DATE_CREATED = "date_created"
    DATE_LAST_UPDATED = "date_last_updated"


class DatasetBase(BaseModel):
    name: str = Field(max_length=255, description="Name of the dataset")
    description: str | None = Field(None, description="Description of the dataset")


class DatasetCreate(DatasetBase):
    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for the dataset",
    )

    @computed_field
    @property
    def date_created(self) -> datetime:
        """Automatically set the creation date to now."""
        return datetime.now(UTC)

    @computed_field
    @property
    def date_last_updated(self) -> datetime:
        """Automatically set the last updated date to now."""
        return datetime.now(UTC)


class DatasetUpdate(BaseModel):
    name: str | None = Field(None, description="Name of the dataset")
    description: str | None = Field(None, description="Description of the dataset")

    @computed_field
    @property
    def date_last_updated(self) -> datetime:
        """Automatically set the last updated date to now."""
        return datetime.now(UTC)


class Dataset(DatasetBase):
    id: str
    date_created: datetime
    date_last_updated: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "My Dataset",
                "description": "A sample dataset",
                "date_created": "2024-01-01T12:00:00Z",
                "date_last_updated": "2024-01-02T12:00:00Z",
            }
        },
    }


class DatasetsRequest(BaseModel):
    query: str | None = Field(
        None, description="Optional search query to filter datasets"
    )
    limit: int = Field(10, description="Number of datasets to return", ge=1, le=100)
    page: int = Field(1, description="Page number for pagination", ge=1)
    sort_by: str | None = Field(None, alias="sortBy")
    sort_order: SortOrder = Field(
        SortOrder.DESC, description="Sort order when listing the dataset"
    )

    @model_validator(mode="after")
    def validate_sort_by(self) -> "DatasetsRequest":
        """Convert sort_by string to enum."""
        if self.sort_by is None:
            self.sort_by = DatasetSortField.NAME
        elif isinstance(self.sort_by, str):
            snake_value = to_snake(self.sort_by)
            try:
                self.sort_by = DatasetSortField(snake_value)
            except ValueError as exc:
                raise ValueError(f"Invalid sort_by: {self.sort_by}") from exc
        return self


class PaginatedDatasetsResponse(PaginatedResponse):
    data: list[Dataset] = Field(description="List of datasets on the current page")
