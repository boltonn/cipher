from datetime import datetime
from enum import StrEnum

from pydantic import Field

from cipher.schemas._base.base import BaseModel
from cipher.schemas.content.document import DocumentMetadata
from cipher.schemas.content.email import EmailMetadata


class ExtractionContentFormat(StrEnum):
    MARKDOWN = "markdown"
    PLAIN = "plain"


class TextExtractor(StrEnum):
    """Which library produced this extraction.

    Configurable per filetype group, not fixed (e.g. kreuzberg for
    `document`, pyparse for `email` by default).
    """

    KREUZBERG = "kreuzberg"
    PYPARSE = "pyparse"


class PrechunkedSpan(BaseModel):
    """A chunk boundary computed by the extractor's own chunker.

    Populated only when the configured chunker for this file was the
    extractor's built-in one (currently only kreuzberg supports this) --
    lets the embedding stage skip splitting entirely for these rows. Fields
    beyond offsets/heading_path mirror xberg's `ChunkMetadata` directly.
    """

    content: str
    start_offset: int
    end_offset: int
    heading_path: list[str] | None = None
    token_count: int | None = Field(
        default=None, description="Token count from xberg's tokenizer-aware sizing, if used"
    )
    first_page: int | None = Field(default=None, description="First page this chunk spans")
    last_page: int | None = Field(default=None, description="Last page this chunk spans")


class ExtractedTextBase(BaseModel):
    """Canonical extracted representation of a file's text.

    This is the expensive-to-produce output of text extraction (parsing,
    OCR) persisted once, so downstream consumers -- chunking/embedding,
    future entity extraction, or re-embedding with a new model -- never need
    to re-run extraction to get at the text. `metadata` is the one place
    content-type-specific fields live -- a `DocumentMetadata` or
    `EmailMetadata` instance, never a loose untyped dict.
    """

    file_id: str
    content: str
    content_format: ExtractionContentFormat = ExtractionContentFormat.PLAIN
    extractor: TextExtractor
    metadata: DocumentMetadata | EmailMetadata | None = None
    prechunked: list[PrechunkedSpan] | None = Field(
        default=None,
        description="Pre-computed chunk boundaries; only set when the extractor's own chunker was used",
    )


class ExtractedTextCreate(ExtractedTextBase):
    """Schema for creating/upserting an extraction result."""

    pass


class ExtractedText(ExtractedTextBase):
    """ExtractedText model for API responses."""

    id: str
    date_created: datetime
    date_last_updated: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "file_id": "123e4567-e89b-12d3-a456-426614174001",
                "content": "# Report\n\nQuarterly summary...",
                "content_format": "markdown",
                "extractor": "kreuzberg",
                "metadata": {"filename": "report.pdf", "page_count": 4, "detected_language": "en"},
                "date_created": "2024-01-01T12:00:00Z",
                "date_last_updated": "2024-01-01T12:00:00Z",
            }
        },
    }
