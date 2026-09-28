"""Abstract interface for chunk retrieval (keyword + semantic + entity + graph).

`PostgresChunkRetrievalRepository` implements this over the `chunk` table joined
to `mention`; an `ElasticsearchChunkRetrievalRepository` could implement the same
contract over the `text_chunks` index. Callers (the `/search` router, the chat
agent) depend on this, not a concrete class -- `RETRIEVAL__BACKEND` selects the
implementation. See docs/retrieval-architecture.md.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from cipher.schemas._base.common import PaginatedResponse
from cipher.schemas.content.results import FileSearchResult  # noqa: F401  (documents `search()` payload)
from cipher.schemas.content.search import RetrievalQuery, TextChunk


@dataclass(frozen=True)
class ChunkSpan:
    """One chunk's identity + character span, for the mention -> chunk bisect."""

    chunk_id: str
    start_offset: int
    end_offset: int


class ChunkRetrievalRepository(ABC):
    """Storage-agnostic chunk retrieval and lifecycle."""

    @abstractmethod
    async def search(self, query: RetrievalQuery) -> PaginatedResponse:
        """Rank chunks by `query.mode`, apply every filter, group by file.

        Returns a `PaginatedResponse` whose `data` is a list of `FileSearchResult`.
        `total` is a true distinct-file count and a page is exactly `limit` files,
        matching the current `/search` contract.
        """

    @abstractmethod
    async def upsert_chunks(self, chunks: list[TextChunk]) -> tuple[int, int]:
        """Insert or replace chunk rows/docs (keyed by `TextChunk.id`). Returns (written, failed)."""

    @abstractmethod
    async def delete_by_file_id(self, file_id: str) -> int:
        """Delete the chunks a file owns as representative. Returns rows removed."""

    @abstractmethod
    async def delete_by_dataset_id(self, dataset_id: str) -> int:
        """Delete every chunk in a dataset. Returns rows removed."""

    @abstractmethod
    async def attach_duplicate(self, *, dataset_id: str, sha256: str, file_id: str) -> bool:
        """Add `file_id` to the `duplicate_file_ids` of this content's chunks (same dataset).

        Returns whether any row matched -- i.e. whether this file's content is
        already stored and it can skip its own chunk/embedding work.
        """

    @abstractmethod
    async def spans_for_file(self, file_id: str) -> list[ChunkSpan]:
        """Every chunk's id + span for a file, ordered by `start_offset`.

        The input to the mention -> chunk assignment at extraction time. Resolves
        through `duplicate_file_ids`, so a content-duplicate file returns the
        shared rows.
        """

    @abstractmethod
    async def ensure_schema(self) -> None:
        """Create the backend's index/mapping if absent (idempotent, startup-safe).

        For Postgres this is the ranker-specific keyword index on `chunk.text`
        (`RETRIEVAL__TEXT_RANKER`); the table and portable indexes come from
        migrations.
        """
