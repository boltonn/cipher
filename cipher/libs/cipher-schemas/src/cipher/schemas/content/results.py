"""Grouped-by-file chunk search result, shared by every retrieval backend.

Lives here (not in a datastore package) so `datastores/base/retrieval.py` and both
adapters can reference one result contract.
"""

from pydantic import Field

from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import PaginatedResponse
from cipher.schemas.content.document import ScoredDocumentTextChunk
from cipher.schemas.content.email import ScoredEmailTextChunk

ScoredTextChunk = ScoredDocumentTextChunk | ScoredEmailTextChunk


class MonthCount(BaseModel):
    """Files in one calendar month (by content date)."""

    month: str = Field(description="`YYYY-MM`")
    files: int


class ResultShape(BaseModel):
    """How a result set is spread: content-date histogram and `filetype_group` mix.

    Computed over the ranked candidate pool (`sample_size` chunks), not the whole
    match set -- "in the top N hits".
    """

    date_histogram: list[MonthCount] = Field(default_factory=list)
    filetype_groups: dict[str, int] = Field(default_factory=dict, description="Files per `filetype_group`")
    sample_size: int = Field(default=0, description="Candidate chunks the shape was computed over")


class FileSearchResult(BaseModel):
    """One file's search hit: its matching chunks in reading order, plus the best one.

    Grouping by file is done by the query/repository, not re-aggregated from a
    flat chunk list by the caller -- so a page is exactly `limit` files (not a
    chunk-dependent count that collapses to fewer) and `total` is a real
    distinct-file count.
    """

    file_id: str
    top_score: float = Field(description="Score of `top_chunk_id` -- what this result ranks/sorts by")
    top_chunk_id: str = Field(description="id of the best-matching chunk within `chunks`")
    match_count: int = Field(description="Total matching chunks in this file, may exceed len(chunks) if capped")
    chunks: list[ScoredTextChunk] = Field(description="Matching chunks, in reading order, capped per file")
    tags: list[str] = Field(
        default_factory=list, description="The file content's current positive tags (read live, not from the index)"
    )
    source_tags: list[str] = Field(default_factory=list, description="Tags that came with the data")
    message_states: list[str] = Field(default_factory=list, description="Message states as the source recorded them")


class PaginatedFileSearchResponse(PaginatedResponse):
    """A page of file results; `total` is exact for browse / keyword search.

    Semantic and hybrid ranking has no natural cut-off (every chunk has *some*
    similarity), so `total` there only counts files in the candidate pool and
    `total_is_exact` is false -- callers shouldn't present it as a result count.
    """

    data: list[FileSearchResult]
    total_is_exact: bool = Field(default=True, description="False when `total` is only the candidate pool's files")
    shape: ResultShape | None = Field(default=None, description="Set when the query asked for `include_shape`")
