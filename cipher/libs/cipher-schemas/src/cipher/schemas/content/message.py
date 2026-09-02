from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import uuid4

import numpy as np
from pydantic import BeforeValidator, ConfigDict, Field, computed_field

from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import PageParams, PaginatedResponse, PhoneNumberType

TEXT_EMBEDDING_DIMENSION = 1024


def coerce_np_to_list(v: Any) -> Any:
    """Coerce a Numpy array to a list."""
    if isinstance(v, np.ndarray):
        return v.flatten().tolist()
    return v


TextEmbedding = Annotated[
    list[float],
    BeforeValidator(coerce_np_to_list),
    Field(min_length=TEXT_EMBEDDING_DIMENSION, max_length=TEXT_EMBEDDING_DIMENSION),
]


class ChunkSortField(StrEnum):
    date = "date"
    RELEVANCE = "_score"
    SIMILARITY = "_knn_score"


class MessageSortField(StrEnum):
    DATE_RECEIVED = "date_received"
    DATE_SENT = "date_sent"
    RELEVANCE = "_score"
    SIMILARITY = "_knn_score"


class MessageStatus(StrEnum):
    INBOX = "inbox"
    SENT = "sent"
    DRAFT = "draft"
    OUTBOX = "outbox"
    FAILED = "failed"
    QUEUED = "queued"


class MessageBase(BaseModel):
    """Base message schema."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    message_id: str
    sender: str
    sender_type: PhoneNumberType
    recipient: str
    recipient_type: PhoneNumberType
    date_sent: datetime | None = None
    date_received: datetime | None = None
    date_read: datetime | None = None
    is_read: bool | None = None
    is_locked: bool = False
    language: str | None = None
    text: str | None = None
    translation: str | None = None
    conversation_id: str
    message_status: MessageStatus
    meaningful_hash: str
    source_type: str | None = None


class MessageFilters(BaseModel):
    """Reusable filter set for message queries.

    All fields are optional — only provided fields are included in ES queries.
    Nested message fields (sender, recipient, etc.) are applied via a nested
    query on the messages path. Top-level fields (device_id, conversation_id)
    are applied as plain term filters.
    """

    device_id: str | None = None
    conversation_id: str | None = None
    sender: str | None = None
    recipient: str | None = None
    message_status: MessageStatus | None = None
    source_type: str | None = None
    language: str | None = None
    is_read: bool | None = None
    is_locked: bool | None = None
    date_sent_from: datetime | None = Field(None, description="Filter messages sent after this date")
    date_sent_to: datetime | None = Field(None, description="Filter messages sent before this date")
    date_received_from: datetime | None = Field(None, description="Filter messages received after this date")
    date_received_to: datetime | None = Field(None, description="Filter messages received before this date")


class MessageUpdate(BaseModel):
    """Message update schema."""

    translation: str | None = None


class Message(MessageBase):
    """Message model for API responses."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    file_id: str | None = None
    device_id: str | None = None

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "message_id": "msg_12345",
                "sender": "+1234567890",
                "sender_type": "mobile",
                "recipient": "+0987654321",
                "recipient_type": "mobile",
                "date_sent": "2024-01-01T12:00:00Z",
                "date_received": "2024-01-01T12:00:01Z",
                "conversation_id": "conv_abc123",
                "message_status": "inbox",
                "text": "Hello, world!",
                "meaningful_hash": "abc123def456",
                "device_id": "123e4567-e89b-12d3-a456-426614174001",
            }
        },
    }


class ConversationChunk(BaseModel):
    """Schema for conversation chunks used in embedding pipeline."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    embedding: TextEmbedding
    messages: list[MessageBase]

    @computed_field
    @property
    def conversation_id(self) -> str:
        """Get conversation ID from first message."""
        # throw error if not all messages have the same conversation_id
        conversation_ids = {msg.conversation_id for msg in self.messages}
        if len(conversation_ids) > 1:
            raise ValueError("All messages in a chunk must have the same conversation_id")
        return self.messages[0].conversation_id

    @computed_field
    @property
    def date(self) -> datetime | None:
        """Get earliest date_received from messages."""
        dates = [msg.date_received for msg in self.messages if msg.date_received]
        return min(dates) if dates else None


class ConversationChunkPublic(BaseModel):
    """Schema for conversation chunks through the API.

    The embedding field is intentionally excluded from the public schema for
    performance reasons. The expectation is you use the chunk ID to retrieve
    the embedding separately when needed, rather than including it in every API
    response, which can be large and slow to serialize/transfer.
    """

    id: str
    messages: list[MessageBase]
    tags: list[str] = Field(default_factory=list)
    negative_tags: list[str] = Field(
        default_factory=list,
        description="List of tags that are close the label but not positive, used for training purposes",
    )

    @computed_field
    @property
    def conversation_id(self) -> str:
        """Get conversation ID from first message."""
        # throw error if not all messages have the same conversation_id
        conversation_ids = {msg.conversation_id for msg in self.messages}
        if len(conversation_ids) > 1:
            raise ValueError("All messages in a chunk must have the same conversation_id")
        return self.messages[0].conversation_id

    @computed_field
    @property
    def date(self) -> datetime | None:
        """Get earliest date_received from messages."""
        dates = [msg.date_received for msg in self.messages if msg.date_received]
        return min(dates) if dates else None


class BaseMessageSearchParameters(PageParams):
    """Base parameters shared across all chunk search and list endpoints."""

    filters: MessageFilters = Field(default_factory=MessageFilters)
    limit: int = Field(10, ge=1, le=10, description="Number of results to return")
    sort_by: ChunkSortField = Field(ChunkSortField.date)

    model_config = {
        "json_schema_extra": {
            "example": {
                "page": 1,
                "limit": 10,
                "sortBy": "date",
                "sortOrder": "desc",
            }
        }
    }


class ConversationChunkListRequest(BaseMessageSearchParameters):
    """Request schema for listing conversation chunks with filters and pagination."""

    pass


class MessageListRequest(BaseMessageSearchParameters):
    """Plain listing of messages with filters and sort — no query or embedding."""

    pass


class BaseMessageTextSearchParameters(BaseMessageSearchParameters):
    """BM25 search over message text and translation within chunks.

    Chunks are scored by their best-matching message (score_mode=max).
    """

    query: str = Field(..., description="Text to search for")
    sort_by: ChunkSortField = Field(ChunkSortField.RELEVANCE)

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "travel",
                "page": 1,
                "limit": 10,
                "sortBy": "_score",
                "sortOrder": "desc",
            }
        }
    }


class TextSearchRequest(BaseMessageTextSearchParameters):
    """Request schema for BM25 search over message text and translation within chunks."""

    return_messages: bool = Field(True, description="Whether to return at the message or chunk level")

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "meet tomorrow",
                "page": 1,
                "limit": 10,
                "sortBy": "_score",
                "sortOrder": "desc",
                "returnMessages": True,
            }
        }
    }


class BaseConversationChunkSimilaritySearchParameters(BaseMessageSearchParameters):
    """Base parameters for embedding-based chunk similarity search."""

    sort_by: ChunkSortField = Field(ChunkSortField.SIMILARITY)
    num_candidates: int = Field(100, ge=10, le=10_000, description="ES kNN candidate pool size")
    min_similarity: float | None = Field(
        None, ge=0.0, le=1.0, description="Minimum cosine similarity threshold (0 to 1)"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "page": 1,
                "limit": 10,
                "sortBy": "_knn_score",
                "minSimilarity": 0.7,
                "sortOrder": "desc",
                "numCandidates": 100,
            }
        }
    }


class ConversationChunkSemanticSearchRequest(BaseConversationChunkSimilaritySearchParameters):
    """kNN search over chunk embeddings using a pre-computed query embedding."""

    embedding: TextEmbedding = Field(..., description="Query embedding vector")


class ConversationChunkHybridSearchRequest(BaseConversationChunkSimilaritySearchParameters):
    """Hybrid RRF search combining BM25 text matching and kNN chunk embedding similarity."""

    query: str = Field(..., description="Text query for BM25 leg")
    embedding: TextEmbedding = Field(..., description="Query embedding vector for kNN leg")
    sort_by: ChunkSortField = Field(ChunkSortField.RELEVANCE)

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "meet tomorrow",
                "page": 1,
                "limit": 10,
                "sortBy": "_score",
                "sortOrder": "desc",
                "numCandidates": 100,
            }
        }
    }


class ConversationChunkByChunkIdRequest(BaseConversationChunkSimilaritySearchParameters):
    """kNN search using an existing chunk's stored embedding as the query vector."""

    chunk_id: str = Field(..., description="ID of chunk whose embedding to search with")

    model_config = {
        "json_schema_extra": {
            "example": {
                "chunkId": "123e4567-e89b-12d3-a456-426614174000",
                "page": 1,
                "limit": 10,
                "minSimilarity": 0.7,
                "sortOrder": "desc",
            }
        }
    }


class ScoredConversationChunk(ConversationChunkPublic):
    """A ConversationChunk decorated with its retrieval score.

    For kNN / semantic search: score is cosine similarity (0-1).
    For BM25 / text search: score is ES relevance score.
    For hybrid RRF: score is the rank-fused score.
    For plain listing: score is 1.0 as a sentinel (no ranking).
    """

    score: float = Field(..., description="Retrieval score from Elasticsearch.")


class ScoredMessage(Message):
    score: float = Field(..., description="Retrieval score from Elasticsearch")


class PaginatedConversationChunksResponse(PaginatedResponse):
    """Paginated response for conversation chunks."""

    data: list[ScoredConversationChunk] = Field(..., description="List of scored conversation chunks")


class PaginatedMessagesResponse(PaginatedResponse):
    """Paginated response for messages."""

    data: list[Message] = Field(..., description="List of messages")


class ChunkContextRequestParams(BaseModel):
    limit: int = Field(default=2, ge=1, le=50)
    cursor: datetime
    is_after: bool = False
