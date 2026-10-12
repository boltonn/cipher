from datetime import UTC, datetime
from typing import Annotated

from pydantic import Field, StringConstraints, computed_field, field_validator

from cipher.schemas._base.base import BaseModel, StrEnum
from cipher.schemas._base.common import PaginatedResponse, SortOrder


class FileInstanceSortField(StrEnum):
    """FileInstance sort field enumeration."""

    FILENAME = "filename"
    DATE_CREATED = "date_created"
    DATE_LAST_UPDATED = "date_last_updated"
    SIZE = "size"


class Compression(StrEnum):
    """Single-stream compression a file was found in: an encoding of one file, never a container."""

    GZIP = "gzip"
    BZIP2 = "bzip2"
    XZ = "xz"
    ZSTD = "zstd"
    LZ4 = "lz4"


class ArchiveSandbox(StrEnum):
    """How `7zz` (7z / rar / iso, and zip members the stdlib can't read) is confined."""

    BEST_EFFORT = "best_effort"  # every layer this machine allows; a missing one is logged
    REQUIRED = "required"  # those archives fail unless every layer applies
    OFF = "off"  # no sandbox, for environments where it gets in 7zz's way; size limits still hold


class CompressionInfo(BaseModel):
    """How a file was compressed when found. The row's own hashes describe the content once decoded."""

    encoding: Compression = Field(description="Compression the file was found in")
    md5: str = Field(description="MD5 of the file as found (compressed)")
    sha256: str = Field(description="SHA256 of the file as found (compressed)")
    size: int = Field(description="Size in bytes of the file as found (compressed)")
    filename: str | None = Field(default=None, description="Original name stored in the compression header (gzip)")
    date_modified: datetime | None = Field(default=None, description="Modified time stored in the header (gzip)")


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
    compression: CompressionInfo | None = Field(
        default=None, description="Set when the file was found compressed (e.g. report.csv.gz, logs.tar.gz)"
    )
    is_encrypted: bool = Field(
        default=False, description="Encrypted as found (an archive with encrypted members, a password-protected file)"
    )

    date_created: datetime | None = Field(default=None, description="Date the file was created")
    date_last_updated: datetime | None = Field(default=None, description="Date the file was last updated")

    @field_validator("path")
    @classmethod
    def validate_path(cls, path: str | None) -> str | None:
        """Ensure path is stored as a resolved string (unset until the file is stored)."""
        return None if path is None else f"/{path.lstrip('/')}"


class File(FileBase):
    """File model for API responses."""

    id: str
    dataset_id: str
    tags: list[str] = Field(default_factory=list, description="Positive labels: the file is this")
    negative_tags: list[str] = Field(
        default_factory=list, description="Negative labels: the file is explicitly not this (hard negatives)"
    )
    tag_scores: dict[str, float] = Field(
        default_factory=dict, description="Model confidence (0-1) that a tag applies; a prediction, not a label"
    )
    source_tags: list[str] = Field(
        default_factory=list, description="Tags that came with the data (e.g. Gmail's inbox categories), not a label"
    )
    message_states: list[str] = Field(
        default_factory=list, description="A message's states as its source recorded them (spam, sent, ...)"
    )

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

    query: str | None = Field(None, description="Optional search query to filter file instances")
    limit: int = Field(10, description="Number of datasets to return", ge=1, le=100)
    page: int = Field(1, description="Page number for pagination", ge=1)
    sort_by: FileInstanceSortField = Field(
        default=FileInstanceSortField.FILENAME,
        description="Default field to sort by when listing the dataset",
    )
    sort_order: SortOrder | None = Field(SortOrder.DESC, description="Default sort order when listing the dataset")

    @field_validator("sort_order")
    def validate_sort_order(cls, value: SortOrder | None) -> SortOrder:
        """Validate sort_order field."""
        if value is None:
            return SortOrder.DESC
        return value


class PaginatedFileResponse(PaginatedResponse):
    data: list[File] = Field(..., description="List of file instances on the current page")


class FileBrowserType(StrEnum):
    """File browser type enumeration."""

    FILE = "file"
    DIRECTORY = "directory"


class FileBrowserItem(FileBase):
    """Schema representing a file or directory in the file browser."""

    id: str | None = Field(default=None, description="File ID (unset for directories)")
    type: FileBrowserType = Field(..., description="Type: file or directory")
    member_count: int = Field(
        default=0, description="Files found inside it -- archive members, email attachments (browse them at its path)"
    )


class FileBrowserRequest(FilesRequest):
    path: str | None = Field(None, description="Directory path to list; None = entire dataset")
    filetype: str | None = Field(None, description="Filter to a specific filetype")
    filetype_group: str | None = Field(None, description="Filter to a specific filetype group")


class FileBrowserResponse(PaginatedResponse):
    data: list[FileBrowserItem] = Field(..., description="List of files and directories in the current path")


class FolderSummary(BaseModel):
    """One folder under a browsed path: how many files sit anywhere below it, of which kinds, and when."""

    path: str = Field(description="Full folder path")
    file_count: int
    filetype_group_counts: dict[str, int] = Field(default_factory=dict)
    date_first: datetime | None = Field(default=None, description="Earliest file date below it")
    date_last: datetime | None = Field(default=None, description="Latest file date below it")


class FiletypeCoverage(BaseModel):
    """How much of one filetype group is reachable by text search."""

    filetype_group: str
    file_count: int
    searchable_count: int = Field(description="Files with extracted, chunked text")


class FilesTagRequest(BaseModel):
    """Label many files' content with one positive tag at once (e.g. the sources an analyst marked relevant)."""

    tag: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    file_ids: list[str] = Field(min_length=1, max_length=500)
