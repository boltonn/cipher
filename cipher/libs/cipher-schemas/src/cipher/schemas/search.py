from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field

from cipher.schemas.base import BaseModel
from cipher.schemas.common import SortOrder


class TextChunk(BaseModel):
    """A contiguous, embedded slice of a parent file's extracted text.

    Shared base for chunk types across content sources (documents, emails,
    and eventually messages) via composition with source-specific metadata
    mixins, e.g. `DocumentTextChunk(DocumentMetadata, TextChunk)` -- keeps
    storage/search concerns common to every chunk (offsets for highlighting,
    dataset/file scoping) in one place.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    dataset_id: str
    file_id: str = Field(description="The chunk's representative file -- see `duplicate_file_ids`")
    sha256: str = Field(description="Content hash of the parent file, used to detect duplicate content")
    duplicate_file_ids: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Other files in the same dataset with identical content (same `sha256`) that "
            "share these chunks instead of storing/embedding their own copy. Always includes `file_id` "
            "itself.",
        ),
    ]
    filetype: str = Field(description="Specific file type of the parent file, e.g. 'pdf', 'docx', 'eml'")
    chunk_index: int = Field(
        description="0-based position of this chunk within its parent's extracted text"
    )
    start_offset: int = Field(
        description="Start character offset within the parent's extracted text"
    )
    end_offset: int = Field(
        description="End character offset within the parent's extracted text"
    )
    text: str
    embedding: Annotated[
        list[float],
        Field(
            default_factory=list,
            description="Vector embedding of the chunk text. Populated when indexing; "
            "empty when read back, since the `text_chunks` index excludes it from "
            "`_source` (large, and never needed by a caller that already has the chunk).",
        ),
    ]
    tags: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Optional tags for categorization or filtering",
        ),
    ]
    keywords: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Optional keywords extracted from the chunk",
        ),
    ]
    date_created: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChunkSortField(StrEnum):
    DATE = "date_created"
    # Covers both BM25 relevance and kNN similarity -- callers shouldn't need
    # to know which underlying ES ranking a given endpoint uses to ask for
    # "sort by how well it matches".
    SCORE = "score"


class ChunkFilters(BaseModel):
    """Reusable filter set for the unified document+email chunk search index."""

    dataset_id: str | None = None
    file_id: str | None = None
    tags: list[str] | None = None
    filetype_group: Literal["document", "email"] | None = Field(
        default=None, description="Restrict to one filetype group; omit to search both"
    )
    filetype: str | None = Field(default=None, description="Restrict to one specific filetype, e.g. 'pdf'")


class BaseChunkSearchParameters(BaseModel):
    """Base parameters shared across document/email chunk search and list endpoints."""

    filters: ChunkFilters = Field(default_factory=ChunkFilters)
    limit: int = Field(10, ge=1, le=100, description="Number of results to return")
    page: int = Field(1, ge=1, description="Page number for pagination")
    sort_by: ChunkSortField = Field(ChunkSortField.DATE)
    sort_order: SortOrder = Field(SortOrder.DESC)

    @property
    def offset(self) -> int:
        """Calculate offset for pagination."""
        return (self.page - 1) * self.limit


class ChunkTextSearchRequest(BaseChunkSearchParameters):
    """BM25 full-text search over chunk text.

    `min_similarity` is only meaningful for the semantic/hybrid endpoints
    (which convert this same request body into a `ChunkSemanticSearchRequest`/
    `ChunkHybridSearchRequest` server-side) -- BM25 scores aren't a bounded
    similarity, so there's no equivalent cutoff for plain text search, and
    the field is ignored there. Pagination for text search instead relies on
    BM25 only ever matching chunks containing a query term, so it naturally
    runs out on its own.
    """

    query: str = Field(..., description="Text to search for")
    sort_by: ChunkSortField = Field(ChunkSortField.SCORE)
    min_similarity: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Minimum similarity threshold for the semantic/hybrid endpoints; ignored for BM25 text search",
    )


class ChunkSemanticSearchRequest(BaseChunkSearchParameters):
    """kNN search over chunk embeddings using a pre-computed query embedding."""

    embedding: Annotated[list[float], Field(description="Query embedding vector")]
    num_candidates: int = Field(100, ge=10, le=10_000, description="ES kNN candidate pool size")
    min_similarity: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Minimum similarity threshold -- unlike BM25, kNN always returns its "
        "requested candidate count regardless of relevance, so this is what gives semantic/"
        "hybrid pagination a real stopping point once nothing left clears the bar",
    )
    sort_by: ChunkSortField = Field(ChunkSortField.SCORE)


class ChunkHybridSearchRequest(ChunkSemanticSearchRequest):
    """Hybrid RRF search combining BM25 text matching and kNN embedding similarity."""

    query: str = Field(..., description="Text query for the BM25 leg")
    sort_by: ChunkSortField = Field(ChunkSortField.SCORE)
