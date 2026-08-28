from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import Field, computed_field, model_validator
from pydantic.alias_generators import to_snake

from cipher.schemas.base import BaseModel
from cipher.schemas.common import PaginatedResponse, SortOrder

HistogramGranularity = Literal["day", "week", "month"]


class DatasetSortField(StrEnum):
    NAME = "name"
    DATE_CREATED = "date_created"
    DATE_LAST_UPDATED = "date_last_updated"
    FILE_COUNT = "file_count"
    TOTAL_SIZE_BYTES = "total_size_bytes"
    FILETYPE_COUNT = "filetype_count"


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


class DatasetSummary(Dataset):
    """A dataset enriched with aggregate stats over its files."""

    file_count: int = Field(0, description="Number of files loaded into this dataset")
    total_size_bytes: int = Field(0, description="Total size in bytes of all files in this dataset")
    filetype_count: int = Field(0, description="Number of distinct file types in this dataset")


class DatasetsRequest(BaseModel):
    query: str | None = Field(
        None, description="Optional search query to filter datasets"
    )
    date_created_from: datetime | None = Field(None, description="Filter datasets created after this date")
    date_created_to: datetime | None = Field(None, description="Filter datasets created before this date")
    date_last_updated_from: datetime | None = Field(
        None, description="Filter datasets last updated after this date"
    )
    date_last_updated_to: datetime | None = Field(
        None, description="Filter datasets last updated before this date"
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
    data: list[DatasetSummary] = Field(description="List of datasets on the current page")


class FiletypeBreakdownItem(BaseModel):
    """File count for a single filetype or filetype group."""

    filetype: str
    count: int


class LoadHistogramBucket(BaseModel):
    """File count for a single time bucket, e.g. one day/week/month."""

    date_bucket: datetime
    count: int


class DatasetStatsRequest(BaseModel):
    """Date range, bucket granularity, and drill-down filters for a dataset's stats breakdown."""

    date_from: datetime | None = Field(None, description="Only include files loaded on/after this date")
    date_to: datetime | None = Field(None, description="Only include files loaded on/before this date")
    granularity: HistogramGranularity = Field("day", description="Time bucket size for the load histogram")
    filetype: str | None = Field(None, description="Only include files of this filetype")
    filetype_group: str | None = Field(None, description="Only include files in this filetype group")


class DatasetStatsResponse(BaseModel):
    """Aggregate stats for a dataset's files, scoped to the requested date range."""

    total_files: int = Field(description="Total files matching the date range")
    total_size_bytes: int = Field(description="Total size in bytes of files matching the date range")
    by_filetype: list[FiletypeBreakdownItem] = Field(description="File count broken down by filetype")
    by_filetype_group: list[FiletypeBreakdownItem] = Field(
        description="File count broken down by filetype group"
    )
    loaded_over_time: list[LoadHistogramBucket] = Field(
        description="File count per time bucket, ordered chronologically"
    )
