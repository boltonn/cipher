import hashlib
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import PageParams
from cipher.schemas.graph.mention import MentionProvenance


def chunk_id_for(*, dataset_id: str, sha256: str, chunk_index: int, start_offset: int) -> str:
    """Deterministic chunk id -- stable across re-embeds so `mention.chunk_id` survives.

    Keyed on `(dataset_id, sha256, chunk_index, start_offset)`, not a random uuid:

    - Re-running embedding with the same chunking reproduces the same ids (a
      re-embed upserts instead of duplicating).
    - Within a dataset, content-identical files (same `sha256`) resolve to the
      same chunk ids -- so they share one chunk record (`duplicate_file_ids`)
      rather than being processed twice, matching the retrieval store's
      same-dataset dedup.
    - `dataset_id` is in the key because chunk storage is per-dataset: a chunk
      carries denormalized `dataset_id`/`tags`, so the same content in another
      dataset is a separate record, not a shared one.

    The value doubles as the retrieval store's document id (Elasticsearch `_id`
    / `chunk.id`).
    """
    return hashlib.sha256(f"{dataset_id}:{sha256}:{chunk_index}:{start_offset}".encode()).hexdigest()


class TextChunk(BaseModel):
    """A contiguous, embedded slice of a parent file's extracted text.

    Shared base for chunk types across content sources (documents, emails,
    and eventually messages) via composition with source-specific metadata
    mixins, e.g. `DocumentTextChunk(DocumentMetadata, TextChunk)` -- keeps
    storage/search concerns common to every chunk (offsets for highlighting,
    dataset/file scoping) in one place.
    """

    id: str = Field(
        default="",
        description="Deterministic id from `chunk_id_for(dataset_id, sha256, chunk_index, start_offset)`; "
        "filled on validation when left blank. Passed explicitly only when reconstructing a chunk "
        "read back from the store.",
    )
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
    chunk_index: int = Field(description="0-based position of this chunk within its parent's extracted text")
    start_offset: int = Field(description="Start character offset within the parent's extracted text")
    end_offset: int = Field(description="End character offset within the parent's extracted text")
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
            description="Tags copied in at indexing time (may be stale) -- read `FileSearchResult.tags` for current ones",
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

    # Denormalized from `mention` rows by `sync-chunk-entities` (runs after
    # extract-selectors / extract-entities). Empty until that step runs.
    entity_ids: list[str] = Field(default_factory=list, description="Resolved entities mentioned in this chunk's span")
    entity_types: list[str] = Field(default_factory=list, description="Distinct entity types mentioned here")
    selector_types: list[str] = Field(default_factory=list, description="Distinct selector types mentioned here")
    selector_subtypes: list[str] = Field(
        default_factory=list, description="Distinct selector subtypes (telegram, btc_address, ...)"
    )
    mention_count: int = Field(default=0, description="Total mentions anchored in this chunk")

    @model_validator(mode="after")
    def _fill_deterministic_id(self) -> "TextChunk":
        if not self.id:
            self.id = chunk_id_for(
                dataset_id=self.dataset_id,
                sha256=self.sha256,
                chunk_index=self.chunk_index,
                start_offset=self.start_offset,
            )
        return self


class RetrievalConfigInfo(BaseModel):
    """What backs chunk search in this deployment right now -- `GET /search/config`.

    `text_ranker_effective` is what will actually run given which Postgres
    extensions are installed; it may be a downgrade from the configured
    `text_ranker` (see docs/postgres-extensions.md).
    """

    backend: str = Field(description="'postgres' | 'elasticsearch'")
    text_ranker: str = Field(description="Configured keyword ranker (postgres backend)")
    text_ranker_effective: str = Field(description="Ranker that will actually run given installed extensions")
    installed_extensions: list[str] = Field(default_factory=list, description="Full-text-relevant extensions present")
    graph_expand_entity_cap: int = Field(description="Max entities a graph_expand fans out to before truncation")


class ChunkSortField(StrEnum):
    DATE = "date_created"
    # Covers both BM25 relevance and kNN similarity -- callers shouldn't need
    # to know which underlying ES ranking a given endpoint uses to ask for
    # "sort by how well it matches".
    SCORE = "score"


class MentionSpan(BaseModel):
    """Where a filtered entity or mention value occurs, in extracted-text offsets."""

    entity_id: str | None = Field(default=None, description="Set when the span matched an `entity_ids` filter")
    normalized_value: str | None = Field(default=None, description="Set when it matched a `mention_values` filter")
    start_offset: int
    end_offset: int


class CorrespondenceFilters(BaseModel):
    """Who-sent-what-to-whom-when filters, matched against email header mentions.

    Each id is an entity id -- a person/organization or an email-address
    selector. A person also matches through the addresses it `has_selector`
    and through its resolved header display name. `sent_from` / `sent_to` match
    ANY of their ids (pass a person plus extra addresses confirmed to be theirs);
    `participants` requires ALL of its ids, so `participants=[a, b]` means
    "emails between a and b". Dates are inclusive days, compared against the
    email's `date_sent` (or a document's `date_content_created`).
    """

    sent_from: list[str] | None = Field(default=None, description="Sender (header from / sender) -- any of")
    sent_to: list[str] | None = Field(default=None, description="Recipient (header to / cc / bcc) -- any of")
    participants: list[str] | None = Field(default=None, description="All of these in any header role")
    date_from: date | None = Field(default=None, description="Sent / authored on or after this day")
    date_to: date | None = Field(default=None, description="Sent / authored on or before this day")

    def has_correspondence_filter(self) -> bool:
        """Whether any sender / recipient / participant / date filter is set."""
        return bool(self.sent_from or self.sent_to or self.participants or self.date_from or self.date_to)


class ChunkFilters(CorrespondenceFilters):
    """Reusable filter set for the unified document+email chunk search index."""

    dataset_id: str | None = None
    dataset_ids: list[str] | None = Field(
        default=None, description="Restrict to any of these datasets (set server-side to the caller's access)"
    )
    file_id: str | None = None
    tags: list[str] | None = None
    filetype_group: Literal["document", "email"] | None = Field(
        default=None, description="Restrict to one filetype group; omit to search both"
    )
    filetype: str | None = Field(default=None, description="Restrict to one specific filetype, e.g. 'pdf'")
    # Entity-aware filters (composable with a text/kNN query; require `sync-chunk-entities`).
    entity_ids: list[str] | None = Field(
        default=None, description="Only chunks that mention every one of these resolved entities"
    )
    mention_values: list[str] | None = Field(
        default=None,
        description="Only files with a mention of every one of these `normalized_value`s, resolved or not "
        "(an IP, a name group) -- file-level, so email header mentions count",
    )
    mention_provenance: list[MentionProvenance] | None = Field(
        default=None,
        description="Where a `mention_values` hit must be found: `text`/`pattern` (written in the body) vs "
        "`email_header` / `metadata` fields; omit for anywhere",
    )
    entity_types: list[str] | None = Field(default=None, description="Only chunks mentioning one of these entity types")
    selector_types: list[str] | None = Field(
        default=None, description="Only chunks mentioning one of these selector types"
    )
    selector_subtypes: list[str] | None = Field(
        default=None, description="Only chunks mentioning one of these subtypes"
    )


class BaseChunkSearchParameters(PageParams):
    """Base parameters shared across document/email chunk search and list endpoints."""

    filters: ChunkFilters = Field(default_factory=ChunkFilters)
    limit: int = Field(10, ge=1, le=100, description="Number of results to return")
    sort_by: ChunkSortField = Field(ChunkSortField.DATE)


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


class RetrievalMode(StrEnum):
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class GraphExpand(BaseModel):
    """Multi-hop graph-RAG expansion spec.

    Walk the entity graph out from the seeds, then keep only chunks from files that
    mention some entity in that expansion -- in the text, or as an email's sender /
    recipient (header participation).
    """

    seed_entity_ids: list[str] = Field(
        min_length=1,
        description="One identity to expand from: an entity plus any extra ids (e.g. addresses) "
        "confirmed to be the same person",
    )
    max_depth: int = Field(1, ge=1, le=3, description="Relationship hops out from the seed")
    min_weight: float = Field(0.0, description="Ignore edges below this weight")
    relationship_types: list[str] | None = Field(
        default=None, description="Restrict the walk to these relationship types; None = all"
    )


class RetrievalQuery(BaseChunkSearchParameters):
    """One query for the unified `ChunkRetrievalRepository.search()`.

    Composes keyword / semantic / entity / graph filtering in a single call
    (docs/retrieval-architecture.md). Entity restrictions live on `filters`
    (`entity_ids`, `entity_types`, `selector_types`, `selector_subtypes`). `text`
    may be empty when an entity or `graph_expand` filter is set -- that's a
    browse, ranked by recency. The legacy `Chunk{Text,Semantic,Hybrid}SearchRequest`
    models are thin constructors over this.
    """

    mode: RetrievalMode = RetrievalMode.HYBRID
    text: str | None = Field(default=None, description="Keyword / hybrid query string")
    embedding: list[float] | None = Field(
        default=None, description="Pre-computed query vector for semantic / hybrid"
    )
    query_language: str | None = Field(
        default=None, description="Language of `text`; picks the FTS config for the `core` keyword ranker"
    )
    graph_expand: GraphExpand | None = None
    min_similarity: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Semantic / hybrid relevance cutoff for pagination"
    )
    sort_by: ChunkSortField = Field(ChunkSortField.SCORE)
