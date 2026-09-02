"""Text chunk repository — Elasticsearch operations for the unified document+email index.

One flat ES document per chunk, discriminated by `filetype_group`, so
"search everything" is a single query rather than a federated one across
separate indices. A hit is validated back into `ScoredDocumentTextChunk` or
`ScoredEmailTextChunk` by its `filetype_group` field.
"""

import re

from elastic_transport import ObjectApiResponse
from loguru import logger
from pydantic import Field
from tqdm import tqdm

from cipher.datastores.elasticsearch.mappings import AnalyzerName, build_text_chunk_mapping
from cipher.datastores.elasticsearch.utils import PaginatedResponse, paginate
from cipher.schemas._base.base import BaseModel
from cipher.schemas.content.document import ScoredDocumentTextChunk
from cipher.schemas.content.email import ScoredEmailTextChunk
from cipher.schemas.content.search import (
    ChunkFilters,
    ChunkHybridSearchRequest,
    ChunkSemanticSearchRequest,
    ChunkSortField,
    ChunkTextSearchRequest,
    TextChunk,
)
from elasticsearch import AsyncElasticsearch, NotFoundError

DEFAULT_INDEX = "text_chunks"

# Vectors are indexed/searchable for kNN but never worth paying to transfer
# back out to a caller that already has the chunk -- every path that returns
# chunks to an API response excludes it. `list_by_file_id` is the one
# exception: `embed_text.py`'s cross-dataset duplicate-content dedup (the
# fallback tier, once `attach_duplicate` finds no same-dataset match) reuses
# another file's already-computed embeddings verbatim via that method, so it
# needs the real vector, not an empty stand-in.
_EXCLUDE_EMBEDDING_SOURCE = {"excludes": ["embedding"]}

ScoredTextChunk = ScoredDocumentTextChunk | ScoredEmailTextChunk

_MODEL_BY_FILETYPE_GROUP: dict[str, type[ScoredTextChunk]] = {
    "document": ScoredDocumentTextChunk,
    "email": ScoredEmailTextChunk,
}

# Matching chunks are capped per file (via `collapse`'s `inner_hits`) so one
# huge file that matches everywhere can't blow up a response -- generous
# enough that any real "step through the matches" UI never notices the cap.
_MAX_MATCHES_PER_FILE = 50


class FileSearchResult(BaseModel):
    """One file's search hit: every one of its matching chunks (reading
    order), plus which one is the best match.

    Grouping by file happens in the Elasticsearch query itself (`collapse`),
    not by re-aggregating a flat chunk list after the fact -- a caller gets
    exactly `limit` files per page (not a variable, chunk-dependent count
    that then has to be re-grouped down to fewer files) and a real
    distinct-file total for pagination, both of which a client-side re-group
    can't provide.
    """

    file_id: str
    top_score: float = Field(description="Score of `top_chunk_id` -- what this result ranks/sorts by")
    top_chunk_id: str = Field(description="id of the best-matching chunk within `chunks`")
    match_count: int = Field(description="Total matching chunks in this file, which may exceed len(chunks) if capped")
    chunks: list[ScoredTextChunk] = Field(description="Matching chunks, in reading order, capped at a max per file")


def _file_id_clause(file_id: str) -> dict:
    """Match chunks belonging to `file_id`, whether stored under it directly or shared via
    `attach_duplicate`.

    `duplicate_file_ids` always includes a chunk's own representative `file_id` for docs
    written after that field existed, but older chunks (indexed before `duplicate_file_ids`
    was added) have no such field at all -- falling back to a plain `file_id` match keeps
    those working without requiring a backfill/re-embed.
    """
    return {
        "bool": {
            "should": [{"term": {"file_id": file_id}}, {"term": {"duplicate_file_ids": file_id}}],
            "minimum_should_match": 1,
        }
    }


def _build_chunk_filters(filters: ChunkFilters) -> list[dict]:
    clauses: list[dict] = []
    if filters.dataset_id is not None:
        clauses.append({"term": {"dataset_id": filters.dataset_id}})
    if filters.file_id is not None:
        clauses.append(_file_id_clause(filters.file_id))
    if filters.tags:
        clauses.append({"terms": {"tags": filters.tags}})
    if filters.filetype_group is not None:
        clauses.append({"term": {"filetype_group": filters.filetype_group}})
    if filters.filetype is not None:
        clauses.append({"term": {"filetype": filters.filetype}})
    return clauses


def _sort_clause(sort_by: ChunkSortField, sort_order: str) -> list[dict] | None:
    if sort_by == ChunkSortField.SCORE:
        return None  # BM25/kNN already rank by score with no explicit sort clause needed.
    return [{sort_by.value: {"order": sort_order}}]


def _bm25_text_query(query: str) -> dict:
    """BM25 match against a chunk's own text, or its file's title -- title only
    qualifies the file's first chunk (`chunk_index` 0), not every chunk.

    `title` is denormalized identically onto every chunk of a file (for
    display), so matching it the same way as `text` would make a title match
    (e.g. searching a document by its own name) a "hit" on every one of that
    file's chunks -- including chunks with no on-topic text of their own to
    show or highlight. Restricting the title path to chunk 0 gives a title
    match exactly one representative hit per file instead.
    """
    return {
        "bool": {
            "should": [
                {"match": {"text": query}},
                {"bool": {"must": [{"match": {"title": query}}, {"term": {"chunk_index": 0}}]}},
            ],
            "minimum_should_match": 1,
        }
    }


def _knn_clause(embedding: list[float], k: int, num_candidates: int, min_similarity: float | None, filters: list[dict]) -> dict:
    """`k` must cover through the end of the requested page (`offset + limit`),
    not just `limit` -- kNN's ranked candidate list is exactly `k` long, and
    `from` then slices into it, so a `k` sized to only one page's worth
    leaves nothing for `from` to slice into past page 1.
    """
    knn: dict = {"field": "embedding", "query_vector": embedding, "k": k, "num_candidates": num_candidates}
    if filters:
        knn["filter"] = {"bool": {"filter": filters}}
    if min_similarity is not None:
        knn["similarity"] = min_similarity
    return knn


# The `text`/`title` highlight clause both BM25-backed searches attach --
# fragments come back with the matched terms wrapped in these tags, which
# `_matched_terms` then extracts so callers get bare words/phrases.
_HIGHLIGHT_CLAUSE = {"fields": {"text": {}, "title": {}}}
_HIGHLIGHT_TAG_RE = re.compile(r"<em>(.*?)</em>")


def _matched_terms(hit: dict) -> list[str]:
    fragments = (f for frags in hit.get("highlight", {}).values() for f in frags)
    # Case-insensitive dedupe: analyzed matches come back in every casing the
    # document used ("Agreement"/"AGREEMENT"), but consumers highlight
    # case-insensitively, so one casing per term is enough.
    unique = {m.casefold(): m for f in fragments for m in _HIGHLIGHT_TAG_RE.findall(f)}
    return list(unique.values())


def _from_hit(hit: dict) -> ScoredTextChunk:
    source = hit["_source"]
    model = _MODEL_BY_FILETYPE_GROUP[source["filetype_group"]]
    score = hit.get("_score") or hit.get("_knn_score") or 1.0
    return model(id=hit["_id"], score=score, highlights=_matched_terms(hit), **source)


# Distinct-file total for pagination, computed by the same query that
# collapses the hits -- a caller needs "how many files matched", not "how
# many chunks matched" (`hits.total`), which `collapse` alone doesn't give.
_FILE_COUNT_AGG = {"file_count": {"cardinality": {"field": "file_id"}}}


def _collapse_clause(highlight: bool) -> dict:
    # No explicit `sort`: leaving `inner_hits` ranked by relevance (its
    # default) keeps each chunk's real `_score` -- sorting by `chunk_index`
    # instead would score every non-representative chunk `null` (ES doesn't
    # compute a relevance score for a sorted hit), which `_from_hit` would
    # then read as a fake 1.0. Reading order is restored in Python afterward
    # (`_file_result_from_hit`), after real scores are already captured.
    inner_hits: dict = {
        "name": "matches",
        "size": _MAX_MATCHES_PER_FILE,
        "_source": _EXCLUDE_EMBEDDING_SOURCE,
    }
    if highlight:
        inner_hits["highlight"] = _HIGHLIGHT_CLAUSE
    return {"field": "file_id", "inner_hits": inner_hits}


def _file_result_from_hit(hit: dict) -> FileSearchResult:
    """Build one file's `FileSearchResult` from its collapsed top-level hit.

    `collapse`'s representative doc (this hit) is the file's best match by
    construction (it's what the outer query sorts by), but `inner_hits`'
    own `size` cap -- relevance-ranked, not reading-order -- can leave it out
    of `chunks` for a file with more matches than the cap. Merged back in
    explicitly so `top_chunk_id` always resolves within `chunks`.

    Note for kNN (`search_semantic`): a collapsed group's `inner_hits` don't
    get a real per-doc kNN score (ES has no per-doc kNN rescore inside
    `inner_hits`), so every chunk but the representative one falls back to
    `_from_hit`'s placeholder score -- only `top_score` is trustworthy there.
    """
    top_chunk = _from_hit(hit)
    inner_hits = hit["inner_hits"]["matches"]["hits"]
    chunks = [_from_hit(h) for h in inner_hits["hits"]]
    if not any(c.id == top_chunk.id for c in chunks):
        chunks.append(top_chunk)
    chunks.sort(key=lambda c: c.chunk_index)
    return FileSearchResult(
        file_id=top_chunk.file_id,
        top_score=top_chunk.score,
        top_chunk_id=top_chunk.id,
        match_count=inner_hits["total"]["value"],
        chunks=chunks,
    )


class ElasticsearchTextChunkRepository:
    """Elasticsearch CRUD/search over the unified document+email chunk index."""

    def __init__(self, client: AsyncElasticsearch, index: str = DEFAULT_INDEX):
        self.client = client
        self.index = index

    async def create_index(self, embedding_size: int, text_analyzer: AnalyzerName = AnalyzerName.ENGLISH) -> bool:
        """Create the index if it does not already exist."""
        if await self.client.indices.exists(index=self.index):
            return False

        resp = await self.client.indices.create(
            index=self.index,
            body=build_text_chunk_mapping(embedding_size=embedding_size, text_analyzer=text_analyzer),
        )
        if not resp.get("acknowledged", False):
            logger.error(f"Failed to create Elasticsearch index '{self.index}': {resp}")
            return False
        logger.success(f"Created Elasticsearch index '{self.index}'")
        return True

    async def delete_index(self) -> bool:
        """Delete the index."""
        resp = await self.client.indices.delete(
            index=self.index, ignore_unavailable=True, master_timeout="5m", timeout="5m"
        )
        return resp.get("acknowledged", False)

    async def get_by_id(self, chunk_id: str) -> ScoredTextChunk | None:
        """Get a single chunk by its ES document ID."""
        try:
            resp: ObjectApiResponse = await self.client.get(
                index=self.index, id=chunk_id, source_excludes="embedding"
            )
        except NotFoundError:
            return None
        return _from_hit({"_id": resp["_id"], "_source": resp["_source"]})

    async def delete(self, chunk_id: str) -> bool:
        """Delete a chunk by its ES document ID."""
        try:
            await self.client.delete(index=self.index, id=chunk_id, refresh=True)
            return True
        except NotFoundError:
            return False

    async def list_by_file_id(self, file_id: str, limit: int = 500) -> list[ScoredTextChunk]:
        """List every chunk belonging to a file, in original document order.

        Unlike the search methods, this is a plain lookup with no relevance
        scoring -- used to reconstruct a file's full extracted text.
        """
        resp = await self.client.search(
            index=self.index,
            body={
                "query": _file_id_clause(file_id),
                "sort": [{"chunk_index": {"order": "asc"}}],
                "size": limit,
            },
        )
        return [_from_hit(hit) for hit in resp["hits"]["hits"]]

    async def attach_duplicate(self, dataset_id: str, sha256: str, file_id: str) -> bool:
        """Share another file's already-indexed chunks with `file_id` instead of storing a copy.

        Only applies if one exists in this dataset with identical content (`sha256`).
        Returns whether a match was found (and `file_id` attached to it). A dataset can
        legitimately contain the same content at multiple paths -- this only shares
        storage *within* one dataset, since a chunk's denormalized `dataset_id`/`tags`
        would otherwise leak one dataset's file identity into another's search results.
        """
        resp = await self.client.update_by_query(
            index=self.index,
            body={
                "query": {
                    "bool": {
                        "filter": [{"term": {"dataset_id": dataset_id}}, {"term": {"sha256": sha256}}],
                    }
                },
                "script": {
                    "lang": "painless",
                    "source": (
                        "if (!ctx._source.duplicate_file_ids.contains(params.file_id)) "
                        "{ ctx._source.duplicate_file_ids.add(params.file_id); }"
                    ),
                    "params": {"file_id": file_id},
                },
            },
            refresh=True,
            ignore_unavailable=True,
            conflicts="proceed",
        )
        return resp.get("updated", 0) > 0

    async def delete_by_file_id(self, file_id: str) -> int:
        """Remove a file's chunks -- e.g. before re-embedding it, or when the file is deleted.

        If other files in the dataset share these exact chunks (`duplicate_file_ids`), the
        docs survive with `file_id` just removed from the list -- reassigning the
        representative `file_id` to a remaining duplicate if it was the one removed --
        instead of deleting content those other files still need. Chunks indexed before
        `duplicate_file_ids` existed have no such field at all; the script treats a missing
        field the same as "no other file shares this" and deletes outright, matching the
        original one-file-per-chunk behavior.

        `conflicts="proceed"`: update_by_query otherwise aborts the whole
        request on a version conflict (e.g. a doc concurrently deleted or
        reindexed since the query snapshot) -- for a purge, a conflicted doc
        is one that's already gone, so skipping it is the desired outcome.
        """
        resp = await self.client.update_by_query(
            index=self.index,
            body={
                "query": _file_id_clause(file_id),
                "script": {
                    "lang": "painless",
                    "source": (
                        "if (ctx._source.duplicate_file_ids == null) { ctx.op = 'delete'; return; } "
                        "ctx._source.duplicate_file_ids.removeIf(id -> id == params.file_id); "
                        "if (ctx._source.duplicate_file_ids.isEmpty()) { ctx.op = 'delete'; } "
                        "else if (ctx._source.file_id == params.file_id) "
                        "{ ctx._source.file_id = ctx._source.duplicate_file_ids[0]; }"
                    ),
                    "params": {"file_id": file_id},
                },
            },
            refresh=True,
            ignore_unavailable=True,
            conflicts="proceed",
        )
        return resp.get("deleted", 0) + resp.get("updated", 0)

    async def delete_by_dataset_id(self, dataset_id: str) -> int:
        """Delete every chunk belonging to a dataset (e.g. before deleting the dataset itself).

        `ignore_unavailable=True` so this is a no-op rather than an error
        when the index hasn't been created yet (a dataset with no
        documents/emails ever extracted/embedded). `conflicts="proceed"` for
        the same reason as `delete_by_file_id` -- an aborted purge here left
        reset-text half-done (chunks partially deleted, enrichments never
        cleared).
        """
        resp = await self.client.delete_by_query(
            index=self.index,
            body={"query": {"term": {"dataset_id": dataset_id}}},
            refresh=True,
            ignore_unavailable=True,
            conflicts="proceed",
        )
        return resp.get("deleted", 0)

    async def count(self, filters: ChunkFilters | None = None) -> int:
        """Count chunk documents, optionally filtered."""
        clauses = _build_chunk_filters(filters) if filters else []
        query = {"bool": {"filter": clauses}} if clauses else {"match_all": {}}
        resp = await self.client.count(index=self.index, body={"query": query})
        return resp["count"]

    async def search_text(self, request: ChunkTextSearchRequest) -> PaginatedResponse[FileSearchResult]:
        """BM25 search over chunk text/title, grouped by file.

        An empty query has no terms for BM25 to match against (and ES would
        just return zero hits), so it falls back to `match_all` -- lets a
        caller browse the (optionally filtered) index before typing anything.
        Score is meaningless for a match_all browse (every hit ties at 1.0),
        so browsing always sorts by date regardless of what was requested.

        Grouping happens via `collapse` in the query itself, not by
        re-aggregating a flat chunk list after the fact: a page is always
        exactly `limit` files (never a chunk-dependent count that then
        collapses down to fewer), and `total` is a real distinct-file count
        (a cardinality agg over this same query) instead of a chunk count.
        """
        clauses = _build_chunk_filters(request.filters)
        is_browsing = not request.query.strip()
        text_query = {"match_all": {}} if is_browsing else _bm25_text_query(request.query)
        sort_by = ChunkSortField.DATE if is_browsing else request.sort_by
        body: dict = {
            "query": {
                "bool": {
                    "must": [text_query],
                    "filter": clauses,
                }
            },
            "from": request.offset,
            "size": request.limit,
            "_source": _EXCLUDE_EMBEDDING_SOURCE,
            "highlight": _HIGHLIGHT_CLAUSE,
            "collapse": _collapse_clause(highlight=True),
            "aggs": _FILE_COUNT_AGG,
        }
        sort = _sort_clause(sort_by, request.sort_order)
        if sort:
            body["sort"] = sort

        resp = await self.client.search(index=self.index, body=body)
        return paginate(
            data=[_file_result_from_hit(hit) for hit in resp["hits"]["hits"]],
            total=resp["aggregations"]["file_count"]["value"],
            page=request.page,
            limit=request.limit,
        )

    async def search_semantic(self, request: ChunkSemanticSearchRequest) -> PaginatedResponse[FileSearchResult]:
        """KNN search over chunk embeddings, grouped by file.

        Comparing raw kNN scores across filetype groups with very different
        typical chunk lengths is a known caveat -- callers wanting apples-
        to-apples ranking across documents and emails should filter to one
        `filetype_group` or normalize scores themselves before merging.

        `total` here is a floor, not exact: kNN only ever ranks within its
        requested candidate pool (`k`), so the cardinality agg only sees
        distinct files inside that pool, not the whole index.
        """
        clauses = _build_chunk_filters(request.filters)
        knn = _knn_clause(
            embedding=request.embedding,
            k=request.offset + request.limit,
            num_candidates=request.num_candidates,
            min_similarity=request.min_similarity,
            filters=clauses,
        )
        resp = await self.client.search(
            index=self.index,
            body={
                "knn": knn,
                "from": request.offset,
                "size": request.limit,
                "_source": _EXCLUDE_EMBEDDING_SOURCE,
                "collapse": _collapse_clause(highlight=False),
                "aggs": _FILE_COUNT_AGG,
            },
        )
        return paginate(
            data=[_file_result_from_hit(hit) for hit in resp["hits"]["hits"]],
            total=resp["aggregations"]["file_count"]["value"],
            page=request.page,
            limit=request.limit,
        )

    async def search_hybrid(self, request: ChunkHybridSearchRequest) -> PaginatedResponse[FileSearchResult]:
        """Hybrid RRF search combining BM25 text matching and kNN embedding similarity, grouped by file.

        Uses the `retriever` RRF form rather than the older top-level `rank`
        parameter -- `collapse` (needed for file-grouping) is only supported
        alongside RRF via a `retriever` tree, not the legacy `rank.rrf` form.

        Unlike plain kNN, the knn leg's `k` here is fixed at `num_candidates`
        rather than growing with `offset + limit`: RRF fuses by each leg's
        *rank position*, not raw score, so changing how many candidates the
        knn leg contributes between page requests shifts which documents
        cross the fusion window and reshuffles the combined ranking -- pages
        stop being stable slices of one ranking and start overlapping.
        """
        clauses = _build_chunk_filters(request.filters)
        knn = _knn_clause(
            embedding=request.embedding,
            k=request.num_candidates,
            num_candidates=request.num_candidates,
            min_similarity=request.min_similarity,
            filters=clauses,
        )
        body: dict = {
            "from": request.offset,
            "size": request.limit,
            "retriever": {
                "rrf": {
                    "retrievers": [
                        {"standard": {"query": {"bool": {"must": [_bm25_text_query(request.query)], "filter": clauses}}}},
                        {"knn": knn},
                    ],
                    "rank_window_size": request.num_candidates,
                    "rank_constant": 60,
                }
            },
            "_source": _EXCLUDE_EMBEDDING_SOURCE,
            "highlight": _HIGHLIGHT_CLAUSE,
            "collapse": _collapse_clause(highlight=True),
            "aggs": _FILE_COUNT_AGG,
        }
        resp = await self.client.search(index=self.index, body=body)
        return paginate(
            data=[_file_result_from_hit(hit) for hit in resp["hits"]["hits"]],
            total=resp["aggregations"]["file_count"]["value"],
            page=request.page,
            limit=request.limit,
        )

    async def _send_batch(self, batch: list[TextChunk]) -> tuple[int, int]:
        operations = []
        for chunk in batch:
            operations.append({"index": {"_index": self.index, "_id": str(chunk.id)}})
            operations.append(chunk.model_dump(exclude={"id"}, by_alias=False, mode="json"))

        resp = await self.client.bulk(operations=operations, refresh=False, timeout=-1)
        failed_items = [item["index"] for item in resp["items"] if item["index"]["status"] not in (200, 201)]
        if failed_items:
            # One reason per distinct error (not one line per doc) -- a bad batch is
            # usually one root cause repeated across many chunks, so this is enough
            # to diagnose without flooding the log.
            reasons = {item["error"]["reason"] for item in failed_items if "error" in item}
            for reason in reasons:
                logger.error(f"Chunk index failure ({sum(1 for i in failed_items if i.get('error', {}).get('reason') == reason)}x): {reason}")
        return len(resp["items"]) - len(failed_items), len(failed_items)

    async def bulk_index(
        self, chunks: list[TextChunk], batch_size: int = 100, show_progress: bool = True
    ) -> tuple[int, int]:
        """Bulk index document/email chunks with internal batching. Returns (indexed, failed).

        `show_progress=False` for callers that already track their own
        higher-level progress bar (e.g. embed_text_workflow) -- a fresh bar
        per call here would otherwise repaint over that one.
        """
        total_indexed = 0
        total_failed = 0

        batches = range(0, len(chunks), batch_size)
        if show_progress:
            batches = tqdm(batches, desc=f"Indexing to {self.index}", unit=" batch")

        for i in batches:
            batch = chunks[i : i + batch_size]
            indexed, failed = await self._send_batch(batch)
            total_indexed += indexed
            total_failed += failed

        await self.client.indices.refresh(index=self.index)
        return total_indexed, total_failed
