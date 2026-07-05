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
    file_id: str
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
        list[float], Field(description="Vector embedding of the chunk text")
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
    RELEVANCE = "_score"
    SIMILARITY = "_knn_score"


class ChunkFilters(BaseModel):
    """Reusable filter set for the unified document+email chunk search index."""

    dataset_id: str | None = None
    file_id: str | None = None
    tags: list[str] | None = None
    content_type: Literal["document", "email"] | None = Field(
        default=None, description="Restrict to one content type; omit to search both"
    )


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
    """BM25 full-text search over chunk text."""

    query: str = Field(..., description="Text to search for")
    sort_by: ChunkSortField = Field(ChunkSortField.RELEVANCE)


class ChunkSemanticSearchRequest(BaseChunkSearchParameters):
    """kNN search over chunk embeddings using a pre-computed query embedding."""

    embedding: Annotated[list[float], Field(description="Query embedding vector")]
    num_candidates: int = Field(100, ge=10, le=10_000, description="ES kNN candidate pool size")
    min_similarity: float | None = Field(
        None, ge=0.0, le=1.0, description="Minimum cosine similarity threshold (0 to 1)"
    )
    sort_by: ChunkSortField = Field(ChunkSortField.SIMILARITY)


class ChunkHybridSearchRequest(ChunkSemanticSearchRequest):
    """Hybrid RRF search combining BM25 text matching and kNN embedding similarity."""

    query: str = Field(..., description="Text query for the BM25 leg")
    sort_by: ChunkSortField = Field(ChunkSortField.RELEVANCE)
