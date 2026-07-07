"""Text chunk repository — Elasticsearch operations for the unified document+email index.

One flat ES document per chunk, discriminated by `filetype_group`, so
"search everything" is a single query rather than a federated one across
separate indices. A hit is validated back into `ScoredDocumentTextChunk` or
`ScoredEmailTextChunk` by its `filetype_group` field.
"""

from elastic_transport import ObjectApiResponse
from loguru import logger
from tqdm import tqdm

from cipher.datastores.elasticsearch.mappings import AnalyzerName, build_text_chunk_mapping
from cipher.datastores.elasticsearch.utils import PaginatedResponse, paginate
from cipher.schemas.document import ScoredDocumentTextChunk
from cipher.schemas.email import ScoredEmailTextChunk
from cipher.schemas.search import (
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
# exception: `embed_text.py`'s duplicate-content dedup reuses another file's
# already-computed embeddings verbatim via that method, so it needs the real
# vector, not an empty stand-in.
_EXCLUDE_EMBEDDING_SOURCE = {"excludes": ["embedding"]}

ScoredTextChunk = ScoredDocumentTextChunk | ScoredEmailTextChunk

_MODEL_BY_FILETYPE_GROUP: dict[str, type[ScoredTextChunk]] = {
    "document": ScoredDocumentTextChunk,
    "email": ScoredEmailTextChunk,
}


def _build_chunk_filters(filters: ChunkFilters) -> list[dict]:
    clauses: list[dict] = []
    if filters.dataset_id is not None:
        clauses.append({"term": {"dataset_id": filters.dataset_id}})
    if filters.file_id is not None:
        clauses.append({"term": {"file_id": filters.file_id}})
    if filters.tags:
        clauses.append({"terms": {"tags": filters.tags}})
    if filters.filetype_group is not None:
        clauses.append({"term": {"filetype_group": filters.filetype_group}})
    if filters.filetype is not None:
        clauses.append({"term": {"filetype": filters.filetype}})
    return clauses


def _sort_clause(sort_by: ChunkSortField, sort_order: str) -> list[dict] | None:
    if sort_by in (ChunkSortField.RELEVANCE, ChunkSortField.SIMILARITY):
        return None
    return [{sort_by.value: {"order": sort_order}}]


def _knn_clause(
    embedding: list[float], limit: int, num_candidates: int, min_similarity: float | None, filters: list[dict]
) -> dict:
    knn: dict = {"field": "embedding", "query_vector": embedding, "k": limit, "num_candidates": num_candidates}
    if filters:
        knn["filter"] = {"bool": {"filter": filters}}
    if min_similarity is not None:
        knn["similarity"] = min_similarity
    return knn


def _from_hit(hit: dict) -> ScoredTextChunk:
    source = hit["_source"]
    model = _MODEL_BY_FILETYPE_GROUP[source["filetype_group"]]
    score = hit.get("_score") or hit.get("_knn_score") or 1.0
    return model(id=hit["_id"], score=score, **source)


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
                "query": {"term": {"file_id": file_id}},
                "sort": [{"chunk_index": {"order": "asc"}}],
                "size": limit,
            },
        )
        return [_from_hit(hit) for hit in resp["hits"]["hits"]]

    async def delete_by_file_id(self, file_id: str) -> int:
        """Delete every chunk belonging to a file (e.g. before re-embedding it)."""
        resp = await self.client.delete_by_query(
            index=self.index,
            body={"query": {"term": {"file_id": file_id}}},
            refresh=True,
            ignore_unavailable=True,
        )
        return resp.get("deleted", 0)

    async def delete_by_dataset_id(self, dataset_id: str) -> int:
        """Delete every chunk belonging to a dataset (e.g. before deleting the dataset itself).

        `ignore_unavailable=True` so this is a no-op rather than an error
        when the index hasn't been created yet (a dataset with no
        documents/emails ever extracted/embedded).
        """
        resp = await self.client.delete_by_query(
            index=self.index,
            body={"query": {"term": {"dataset_id": dataset_id}}},
            refresh=True,
            ignore_unavailable=True,
        )
        return resp.get("deleted", 0)

    async def count(self, filters: ChunkFilters | None = None) -> int:
        """Count chunk documents, optionally filtered."""
        clauses = _build_chunk_filters(filters) if filters else []
        query = {"bool": {"filter": clauses}} if clauses else {"match_all": {}}
        resp = await self.client.count(index=self.index, body={"query": query})
        return resp["count"]

    async def search_text(self, request: ChunkTextSearchRequest) -> PaginatedResponse[ScoredTextChunk]:
        """BM25 search over chunk text/title, across documents and emails unless filtered."""
        clauses = _build_chunk_filters(request.filters)
        body: dict = {
            "query": {
                "bool": {
                    "must": [{"multi_match": {"query": request.query, "fields": ["text", "title"]}}],
                    "filter": clauses,
                }
            },
            "from": request.offset,
            "size": request.limit,
            "_source": _EXCLUDE_EMBEDDING_SOURCE,
        }
        sort = _sort_clause(request.sort_by, request.sort_order)
        if sort:
            body["sort"] = sort

        resp = await self.client.search(index=self.index, body=body)
        return paginate(
            data=[_from_hit(hit) for hit in resp["hits"]["hits"]],
            total=resp["hits"]["total"]["value"],
            page=request.page,
            limit=request.limit,
        )

    async def search_semantic(self, request: ChunkSemanticSearchRequest) -> PaginatedResponse[ScoredTextChunk]:
        """KNN search over chunk embeddings, scored by cosine similarity.

        Comparing raw kNN scores across filetype groups with very different
        typical chunk lengths is a known caveat -- callers wanting apples-
        to-apples ranking across documents and emails should filter to one
        `filetype_group` or normalize scores themselves before merging.
        """
        clauses = _build_chunk_filters(request.filters)
        knn = _knn_clause(
            embedding=request.embedding,
            limit=request.limit,
            num_candidates=request.num_candidates,
            min_similarity=request.min_similarity,
            filters=clauses,
        )
        resp = await self.client.search(
            index=self.index,
            body={"knn": knn, "size": request.limit, "_source": _EXCLUDE_EMBEDDING_SOURCE},
        )
        return paginate(
            data=[_from_hit(hit) for hit in resp["hits"]["hits"]],
            total=resp["hits"]["total"]["value"],
            page=request.page,
            limit=request.limit,
        )

    async def search_hybrid(self, request: ChunkHybridSearchRequest) -> PaginatedResponse[ScoredTextChunk]:
        """Hybrid RRF search combining BM25 text matching and kNN embedding similarity."""
        clauses = _build_chunk_filters(request.filters)
        knn = _knn_clause(
            embedding=request.embedding,
            limit=request.limit,
            num_candidates=request.num_candidates,
            min_similarity=request.min_similarity,
            filters=clauses,
        )
        body: dict = {
            "size": request.limit,
            "query": {
                "bool": {
                    "must": [{"multi_match": {"query": request.query, "fields": ["text", "title"]}}],
                    "filter": clauses,
                }
            },
            "knn": knn,
            "rank": {"rrf": {"window_size": request.num_candidates, "rank_constant": 60}},
            "_source": _EXCLUDE_EMBEDDING_SOURCE,
        }
        count_resp = await self.client.count(index=self.index, body={"query": body["query"]})
        resp = await self.client.search(index=self.index, body=body)
        return paginate(
            data=[_from_hit(hit) for hit in resp["hits"]["hits"]],
            total=count_resp["count"],
            page=request.page,
            limit=request.limit,
        )

    async def _send_batch(self, batch: list[TextChunk]) -> tuple[int, int]:
        operations = []
        for chunk in batch:
            operations.append({"index": {"_index": self.index, "_id": str(chunk.id)}})
            operations.append(chunk.model_dump(exclude={"id"}, by_alias=False, mode="json"))

        resp = await self.client.bulk(operations=operations, refresh=False, timeout=-1)
        indexed = sum(1 for item in resp["items"] if item["index"]["status"] in (200, 201))
        return indexed, len(resp["items"]) - indexed

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
