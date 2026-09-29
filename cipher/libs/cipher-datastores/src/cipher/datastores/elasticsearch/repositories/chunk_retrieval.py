"""Elasticsearch implementation of `ChunkRetrievalRepository`.

BM25 / kNN / RRF over the `text_chunks` index, exactly as `ElasticsearchTextChunkRepository`
always has. Entity / selector / graph filters are **not** denormalized onto the chunk
doc (that was the retired `sync-chunk-entities` design, an O(files) batch job that
didn't scale). Instead they're resolved live, at query time, from Postgres
`mention.chunk_id` (and `entity_relationship` for `graph_expand`) into a chunk-id
list, which becomes one `terms` filter ANDed into the same ES query -- no mapping
changes, no sync step, no staleness window.

`mention.chunk_id` needs `chunk` rows to bisect against regardless of which
retrieval backend is active, so this adapter also mirrors chunk identity + spans
into Postgres on every write -- `upsert_chunk_spans` (id/dataset/file/text/language,
**not** embedding, so the expensive part of a chunk is never duplicated).

See docs/retrieval-architecture.md.
"""

from cipher.datastores.base.retrieval import ChunkRetrievalRepository, ChunkSpan
from cipher.datastores.elasticsearch.repositories.text_chunk import (
    DEFAULT_INDEX,
    ElasticsearchTextChunkRepository,
)
from cipher.datastores.postgres.repositories.chunk_retrieval import PostgresChunkRetrievalRepository
from cipher.datastores.postgres.repositories.mention import PostgresMentionRepository
from cipher.datastores.postgres.tables.chunk import CHUNK_EMBEDDING_DIMENSION
from cipher.schemas._base.common import PaginatedResponse
from cipher.schemas.content.results import FileSearchResult  # noqa: F401  (documents search() payload)
from cipher.schemas.content.search import (
    ChunkHybridSearchRequest,
    ChunkSemanticSearchRequest,
    ChunkTextSearchRequest,
    RetrievalMode,
    RetrievalQuery,
    TextChunk,
)

_GRAPH_EXPAND_FILTER_CAP = 10_000


class ElasticsearchChunkRetrievalRepository(ChunkRetrievalRepository):
    def __init__(
        self,
        *,
        client,
        session,
        graph_repo=None,
        graph_expand_entity_cap: int = _GRAPH_EXPAND_FILTER_CAP,
        index: str = DEFAULT_INDEX,
    ):
        self.es = ElasticsearchTextChunkRepository(client=client, index=index)
        self.session = session
        self.mentions = PostgresMentionRepository(session=session)
        # Identity/span mirror only (upsert_chunk_spans never writes embedding).
        self.spans = PostgresChunkRetrievalRepository(session=session)
        self.graph_repo = graph_repo
        self.graph_expand_entity_cap = graph_expand_entity_cap

    # ---- lifecycle -------------------------------------------------------

    async def ensure_schema(self) -> None:
        """Create the ES index if missing (idempotent; no-op if it already exists)."""
        await self.es.create_index(embedding_size=CHUNK_EMBEDDING_DIMENSION)

    # ---- writes --------------------------------------------------------

    async def upsert_chunks(self, chunks: list[TextChunk]) -> tuple[int, int]:
        """Index to ES; mirror identity + spans (no embedding) into Postgres."""
        indexed, failed = await self.es.bulk_index(chunks, show_progress=False)
        await self.spans.upsert_chunk_spans(chunks)
        return indexed, failed

    # Aliases so this repo is a drop-in for the raw `ElasticsearchTextChunkRepository`
    # in the embed pipeline (same method names it already calls).
    async def bulk_index(self, chunks: list[TextChunk], show_progress: bool = False) -> tuple[int, int]:
        """Alias for `upsert_chunks` (embed-pipeline drop-in)."""
        return await self.upsert_chunks(chunks)

    async def list_by_file_id(self, file_id: str, limit: int = 500) -> list[TextChunk]:
        """A file's chunks straight from ES, incl. embedding (cross-dataset clone read)."""
        return await self.es.list_by_file_id(file_id, limit=limit)

    async def delete_by_file_id(self, file_id: str) -> int:
        """Delete from ES and the Postgres span mirror."""
        n = await self.es.delete_by_file_id(file_id)
        await self.spans.delete_by_file_id(file_id)
        return n

    async def delete_by_dataset_id(self, dataset_id: str) -> int:
        """Delete from ES and the Postgres span mirror."""
        n = await self.es.delete_by_dataset_id(dataset_id)
        await self.spans.delete_by_dataset_id(dataset_id)
        return n

    async def attach_duplicate(self, *, dataset_id: str, sha256: str, file_id: str) -> bool:
        """Add `file_id` to the `duplicate_file_ids` of this content's chunks, in both stores."""
        attached = await self.es.attach_duplicate(dataset_id=dataset_id, sha256=sha256, file_id=file_id)
        await self.spans.attach_duplicate(dataset_id=dataset_id, sha256=sha256, file_id=file_id)
        return attached

    async def spans_for_file(self, file_id: str) -> list[ChunkSpan]:
        """Read from the Postgres span mirror (identity + offsets only)."""
        return await self.spans.spans_for_file(file_id)

    # ---- search -------------------------------------------------------

    async def _resolve_extra_filter(self, query: RetrievalQuery) -> tuple[dict | None, bool]:
        """Entity/graph filter as an ES `terms` clause on `_id`, resolved via Postgres.

        Returns `(clause, requested)` -- `requested` distinguishes "no entity/graph
        filter was asked for" from "one was asked for and matched nothing".
        """
        f = query.filters
        graph_ids = None
        if query.graph_expand and self.graph_repo:
            g = query.graph_expand
            graph = await self.graph_repo.traverse(
                start_entity_id=g.seed_entity_id,
                max_depth=g.max_depth,
                min_weight=g.min_weight,
                relationship_types=g.relationship_types,
                limit=self.graph_expand_entity_cap,
            )
            graph_ids = list({n.id for n in graph.nodes} | {g.seed_entity_id})[: self.graph_expand_entity_cap]

        requested = bool(f.entity_ids or f.entity_types or f.selector_types or f.selector_subtypes or graph_ids)
        if not requested:
            return None, False

        chunk_ids = await self.mentions.chunk_ids_for_filter(
            dataset_id=f.dataset_id,
            entity_ids=f.entity_ids,
            entity_types=f.entity_types,
            selector_types=f.selector_types,
            selector_subtypes=f.selector_subtypes,
            graph_entity_ids=graph_ids,
            limit=self.graph_expand_entity_cap,
        )
        return {"terms": {"_id": chunk_ids}}, True  # `chunk_ids == []` is valid ES DSL and matches nothing

    async def search(self, query: RetrievalQuery) -> PaginatedResponse:
        """Rank chunks (keyword / semantic / hybrid / browse), filter, group by file."""
        if query.filters.has_correspondence_filter():
            raise ValueError("sent_from / sent_to / participants / date filters need the postgres retrieval backend")
        extra_filter, _ = await self._resolve_extra_filter(query)

        has_text = bool(query.text and query.text.strip())
        has_vec = query.embedding is not None
        mode = query.mode
        if mode == RetrievalMode.KEYWORD and not has_text:
            mode = RetrievalMode.SEMANTIC if has_vec else RetrievalMode.HYBRID

        # `_build_chunk_filters` still knows how to filter on entity_ids/entity_types/
        # selector_types/selector_subtypes as denormalized per-doc ES fields (the
        # retired sync-chunk-entities design) -- those fields are never populated by
        # this adapter, so a stale `{"term": {"entity_ids": ...}}` clause would AND
        # in and always match nothing. Strip them; `extra_filter` is how this adapter
        # applies them (resolved live via Postgres, above).
        clean_filters = query.filters.model_copy(
            update={"entity_ids": None, "entity_types": None, "selector_types": None, "selector_subtypes": None}
        )
        common = dict(filters=clean_filters, page=query.page, limit=query.limit, sort_order=query.sort_order)
        if mode == RetrievalMode.SEMANTIC and has_vec:
            req = ChunkSemanticSearchRequest(
                embedding=query.embedding, min_similarity=query.min_similarity, **common
            )
            return await self.es.search_semantic(req, extra_filter=extra_filter)
        if mode == RetrievalMode.HYBRID and has_vec:
            req = ChunkHybridSearchRequest(
                query=query.text or "", embedding=query.embedding, min_similarity=query.min_similarity, **common
            )
            return await self.es.search_hybrid(req, extra_filter=extra_filter)
        req = ChunkTextSearchRequest(query=query.text or "", min_similarity=query.min_similarity, **common)
        return await self.es.search_text(req, extra_filter=extra_filter)

    # ---- legacy request-model shims (so existing /search routes are untouched) ----

    async def search_text(self, request: ChunkTextSearchRequest) -> PaginatedResponse:
        """`ChunkTextSearchRequest` -> `search(mode=keyword)`."""
        return await self.search(
            RetrievalQuery(
                mode=RetrievalMode.KEYWORD, text=request.query, filters=request.filters,
                page=request.page, limit=request.limit, sort_order=request.sort_order,
            )
        )

    async def search_semantic(self, request: ChunkSemanticSearchRequest) -> PaginatedResponse:
        """`ChunkSemanticSearchRequest` -> `search(mode=semantic)`."""
        return await self.search(
            RetrievalQuery(
                mode=RetrievalMode.SEMANTIC, embedding=list(request.embedding), filters=request.filters,
                min_similarity=request.min_similarity, page=request.page, limit=request.limit,
                sort_order=request.sort_order,
            )
        )

    async def search_hybrid(self, request: ChunkHybridSearchRequest) -> PaginatedResponse:
        """`ChunkHybridSearchRequest` -> `search(mode=hybrid)`."""
        return await self.search(
            RetrievalQuery(
                mode=RetrievalMode.HYBRID, text=request.query, embedding=list(request.embedding),
                filters=request.filters, min_similarity=request.min_similarity, page=request.page,
                limit=request.limit, sort_order=request.sort_order,
            )
        )
