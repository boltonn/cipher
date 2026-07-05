from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field, computed_field, field_validator
from pydantic.alias_generators import to_snake

from cipher.schemas.base import BaseModel
from cipher.schemas.common import PaginatedResponse, SortOrder


class FileInstanceSortField(StrEnum):
    """FileInstance sort field enumeration."""

    FILENAME = "filename"
    DATE_CREATED = "date_created"
    DATE_LAST_UPDATED = "date_last_updated"
    SIZE = "size"


class FileBase(BaseModel):
    """Base file schema."""

    filename: str = Field(description="Name of the file")
    filetype_group: str = Field(description="Group of the file type")
    filetype: str = Field(description="Specific type of the file")
    filetype_name: str | None = Field(default=None, description="Human-readable name")
    md5: str = Field(description="MD5 hash of the file")
    sha256: str = Field(description="SHA256 hash of the file")
    mime_type: str = Field(description="MIME type of the file")
    path: str | None = Field(default=None, description="Fully normalized absolute path")
    uri: str | None = Field(default=None, description="URI of the file")
    device: str | None = Field(default=None, description="Storage device/bucket/mount the file lives on")
    size: int = Field(description="Size of the file in bytes")
    parent_id: str | None = Field(
        default=None, description="Parent file this was extracted from, e.g. an email attachment's source email"
    )

    date_created: datetime | None = Field(
        default=None, description="Date the file was created"
    )
    date_last_updated: datetime | None = Field(
        default=None, description="Date the file was last updated"
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, path: str) -> str:
        """Ensure path is stored as a resolved string."""
        return f"/{path.lstrip('/')}"


class File(FileBase):
    """File model for API responses."""

    id: str
    dataset_id: str

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "dataset_id": "123e4567-e89b-12d3-a456-426614174002",
                "filename": "example.png",
                "path": "/data/images/example.png",
                "uri": "s3://my-bucket/example.png",
                "device": "s3://my-bucket",
                "filetype_group": "image",
                "filetype": "png",
                "filetype_name": "PNG Image",
                "md5": "d41d8cd98f00b204e9800998ecf8427e",
                "sha256": "e3b0c44298fc1c149afbfc8996fb92427ae41e4649b934ca495991b7852b855",
                "mime_type": "image/png",
                "size": 2048,
                "date_created": "2024-01-01T12:00:00Z",
                "date_last_updated": "2024-01-02T12:00:00Z",
            }
        },
    }


class FileCreate(FileBase):
    """Schema for creating a file."""

    dataset_id: str

    @computed_field
    @property
    def date_loaded(self) -> datetime:
        """Set date_loaded to current time when creating a file."""
        return datetime.now(UTC)


class FileUpdate(BaseModel):
    """Schema for updating file metadata."""

    date_last_updated: datetime | None = None
    device: str | None = None


class FilesRequest(BaseModel):
    """File instances request schema."""

    query: str | None = Field(
        None, description="Optional search query to filter file instances"
    )
    limit: int = Field(10, description="Number of datasets to return", ge=1, le=100)
    page: int = Field(1, description="Page number for pagination", ge=1)
    sort_by: str | None = Field(
        FileInstanceSortField.FILENAME,
        description="Default field to sort by when listing the dataset",
    )
    sort_order: SortOrder | None = Field(
        SortOrder.DESC, description="Default sort order when listing the dataset"
    )

    @field_validator("sort_by", mode="after")
    def validate_sort_by(
        cls, value: FileInstanceSortField | None
    ) -> FileInstanceSortField:
        """Validate sort_by field."""
        if value is None:
            return FileInstanceSortField.FILENAME

        # Convert to snake_case BEFORE Pydantic checks the Enum members
        if isinstance(value, str):
            value = to_snake(value)

        if value not in {
            FileInstanceSortField.FILENAME,
            FileInstanceSortField.DATE_CREATED,
            FileInstanceSortField.DATE_LAST_UPDATED,
        }:
            raise ValueError(
                "sort_by must be one of 'name', 'date_created', or 'date_last_updated'"
            )
        return value

    @field_validator("sort_order")
    def validate_sort_order(cls, value: SortOrder | None) -> SortOrder:
        """Validate sort_order field."""
        if value is None:
            return SortOrder.DESC
        return value


class PaginatedFileResponse(PaginatedResponse):
    data: list[File] = Field(
        ..., description="List of file instances on the current page"
    )


class FileBrowserType(StrEnum):
    """File browser type enumeration."""

    FILE = "file"
    DIRECTORY = "directory"


class FileBrowserItem(FileBase):
    """Schema representing a file or directory in the file browser."""

    type: FileBrowserType = Field(..., description="Type: file or directory")


class FileBrowserRequest(FilesRequest):
    path: str | None = Field(
        None, description="Directory path to list; None = entire dataset"
    )


class FileBrowserResponse(PaginatedResponse):
    data: list[FileBrowserItem] = Field(
        ..., description="List of files and directories in the current path"
    )
