"""Conversation chunk repository — Elasticsearch operations for message chunks."""

from datetime import datetime

# from pprint import pprint
from elastic_transport import ObjectApiResponse
from loguru import logger
from tqdm import tqdm

from cipher.datastores.elasticsearch.mappings import AnalyzerName, build_messages_mapping
from cipher.datastores.elasticsearch.utils import PaginatedResponse, paginate
from cipher.schemas._base.common import ModelTagType
from cipher.schemas.content.message import (
    TEXT_EMBEDDING_DIMENSION,
    ChunkSortField,
    ConversationChunk,
    ConversationChunkByChunkIdRequest,
    ConversationChunkHybridSearchRequest,
    ConversationChunkListRequest,
    ConversationChunkSemanticSearchRequest,
    Message,
    MessageFilters,
    PaginatedConversationChunksResponse,
    PaginatedMessagesResponse,
    ScoredConversationChunk,
    ScoredMessage,
    TextEmbedding,
    TextSearchRequest,
)
from elasticsearch import AsyncElasticsearch, NotFoundError

DEFAULT_INDEX = "messages"


def _build_nested_filters(filters: MessageFilters) -> list[dict]:
    """Build ES filter clauses from a MessageFilters instance.

    device_id and conversation_id are top-level document fields — plain term filters.
    All other fields live on nested messages and are collapsed into a single nested
    query on the messages path.
    """
    top_level: list[dict] = []
    nested_must: list[dict] = []

    if filters.device_id is not None:
        top_level.append({"term": {"device_id": str(filters.device_id)}})
    if filters.conversation_id is not None:
        top_level.append({"term": {"conversation_id": filters.conversation_id}})
    if filters.sender is not None:
        nested_must.append({"term": {"messages.sender": filters.sender}})
    if filters.recipient is not None:
        nested_must.append({"term": {"messages.recipient": filters.recipient}})
    if filters.message_status is not None:
        nested_must.append(
            {"term": {"messages.message_status": filters.message_status.value}}
        )
    if filters.source_type is not None:
        nested_must.append({"term": {"messages.source_type": filters.source_type}})
    if filters.language is not None:
        nested_must.append({"term": {"messages.language": filters.language}})
    if filters.is_read is not None:
        nested_must.append({"term": {"messages.is_read": filters.is_read}})
    if filters.is_locked is not None:
        nested_must.append({"term": {"messages.is_locked": filters.is_locked}})

    date_sent_range: dict = {}
    if filters.date_sent_from:
        date_sent_range["gte"] = filters.date_sent_from.isoformat()
    if filters.date_sent_to:
        date_sent_range["lte"] = filters.date_sent_to.isoformat()
    if date_sent_range:
        nested_must.append({"range": {"messages.date_sent": date_sent_range}})

    date_received_range: dict = {}
    if filters.date_received_from:
        date_received_range["gte"] = filters.date_received_from.isoformat()
    if filters.date_received_to:
        date_received_range["lte"] = filters.date_received_to.isoformat()
    if date_received_range:
        nested_must.append({"range": {"messages.date_received": date_received_range}})

    if nested_must:
        top_level.append(
            {
                "nested": {
                    "path": "messages",
                    "query": {"bool": {"must": nested_must}},
                }
            }
        )

    return top_level


def _sort_clause(sort_by: ChunkSortField, sort_order: str) -> list[dict] | None:
    """Return an ES sort clause, or None for score-based sorts (ES handles those by default)."""
    if sort_by in (ChunkSortField.RELEVANCE, ChunkSortField.SIMILARITY):
        return None
    # date is denormalized to the top-level chunk document for efficient sorting
    return [{"date": {"order": sort_order}}]


def _knn_clause(
    embedding: TextEmbedding,
    limit: int,
    num_candidates: int,
    min_similarity: float | None,
    filters: list[dict],
) -> dict:
    knn: dict = {
        "field": "embedding",
        "query_vector": embedding,
        "k": limit,
        "num_candidates": num_candidates,
    }
    if filters:
        knn["filter"] = {"bool": {"filter": filters}}
    if min_similarity is not None:
        knn["similarity"] = min_similarity
    return knn


def _inner_hits_clause() -> dict:
    return {
        "size": 10,
        "highlight": {
            "fields": {
                "messages.text": {},
                "messages.translation": {},
            }
        },
    }


def _chunk_from_hit(hit: dict) -> ScoredConversationChunk:
    source = hit["_source"]
    return ScoredConversationChunk(
        id=hit["_id"],
        messages=source["messages"],
        embedding=source.get("embedding", []),
        score=hit.get("_score") or hit.get("_knn_score", 1.0),
    )


def _messages_from_hit(hit: dict) -> list[ScoredMessage]:
    """Extract inner_hit messages from a single chunk hit, inheriting the chunk score."""
    chunk_score = hit.get("_score") or hit.get("_knn_score", 1.0)
    inner = (
        hit.get("inner_hits", {}).get("messages", {}).get("hits", {}).get("hits", [])
    )
    return [
        ScoredMessage(
            **inner_hit["_source"],
            score=inner_hit.get("_score") or chunk_score,
        )
        for inner_hit in inner
    ]


def _extract(
    resp: ObjectApiResponse,
    total: int,
    page: int,
    limit: int,
    return_messages: bool,
) -> PaginatedResponse[ScoredConversationChunk] | PaginatedResponse[ScoredMessage]:
    if return_messages:
        messages = []
        for hit in resp["hits"]["hits"]:
            messages.extend(_messages_from_hit(hit))
        return paginate(data=messages, total=total, page=page, limit=limit)
    return paginate(
        data=[_chunk_from_hit(hit) for hit in resp["hits"]["hits"]],
        total=total,
        page=page,
        limit=limit,
    )


class ElasticsearchMessageRepository:
    def __init__(self, client: AsyncElasticsearch, index: str = DEFAULT_INDEX):
        self.client = client
        self.index = index

    async def create_index(
        self,
        embedding_size: int = TEXT_EMBEDDING_DIMENSION,
        text_analyzer: AnalyzerName = AnalyzerName.ENGLISH,
    ) -> bool:
        """Create the message index if it does not already exist.

        Args:
            embedding_size: Embedding dimension — must match the model used in the pipeline.
            text_analyzer: Analyzer to use for the source text field.
        """
        if await self.client.indices.exists(index=self.index):
            return

        resp = await self.client.indices.create(
            index=self.index,
            body=build_messages_mapping(
                embedding_size=embedding_size, text_analyzer=text_analyzer
            ),
        )
        if not resp.get("acknowledged", False):
            logger.error(f"Failed to create Elasticsearch index '{self.index}': {resp}")
            return False
        logger.success(
            f"Created Elasticsearch index '{self.index}' with mapping: {resp.get('acknowledged', False)}"
        )
        return True

    async def delete_index(self) -> bool:
        """Delete the message index."""
        resp = await self.client.indices.delete(
            index=self.index, ignore_unavailable=True, master_timeout="5m", timeout="5m"
        )
        return resp.get("acknowledged", False)

    async def get_chunk_by_id(self, chunk_id: str) -> ScoredConversationChunk | None:
        """Get a chunk document by its ES document ID."""
        try:
            resp: ObjectApiResponse = await self.client.get(
                index=self.index, id=chunk_id
            )
        except NotFoundError:
            return None
        return _chunk_from_hit(resp)

    async def get_message_by_id(self, message_id: str) -> Message | None:
        """Get a single message by its source message_id (e.g. 'sms_42') using inner_hits."""
        resp = await self.client.search(
            index=self.index,
            body={
                "query": {
                    "nested": {
                        "path": "messages",
                        "query": {"term": {"messages.id": message_id}},
                        "inner_hits": {"size": 1},
                    }
                },
                "size": 1,
            },
        )
        hits = resp["hits"]["hits"]
        if not hits:
            return None
        inner_hits = (
            hits[0]
            .get("inner_hits", {})
            .get("messages", {})
            .get("hits", {})
            .get("hits", [])
        )
        if not inner_hits:
            return None
        return Message.model_validate(inner_hits[0]["_source"])

    async def get_chunk_embedding_by_id(self, chunk_id: str) -> TextEmbedding | None:
        """Retrieve the chunk embedding given the chunk id."""
        chunk = await self.get_chunk_by_id(chunk_id)
        return chunk.embedding if chunk else None

    async def translate_message(self, message_id: str, translation: str) -> bool:
        """Update the translation field of a message identified by its id.

        This means the unique id for the nested object that is the message
        as opposed to the message_id field which is the not guaranteed to be unique.
        """
        # dont use script since the nested object should have an _id
        resp = await self.client.update_by_query(
            index=self.index,
            body={
                "script": {
                    "source": "ctx._source.messages.find(m -> m.id == params.id).translation = params.translation",
                    "lang": "painless",
                    "params": {"id": message_id, "translation": translation},
                },
                "query": {
                    "nested": {
                        "path": "messages",
                        "query": {"term": {"messages.id": message_id}},
                    }
                },
            },
            refresh=True,
        )
        return resp.get("updated", 0) > 0

    async def delete_chunk(self, chunk_id: str) -> bool:
        """Delete a chunk document by its ES document ID."""
        try:
            await self.client.delete(index=self.index, id=chunk_id, refresh=True)
            return True
        except NotFoundError:
            return False

    async def chunk_exists_by_hash(self, meaningful_hash: str) -> bool:
        """Check if any chunk contains a message with this deduplication hash."""
        resp = await self.client.count(
            index=self.index,
            body={
                "query": {
                    "nested": {
                        "path": "messages",
                        "query": {
                            "term": {"messages.meaningful_hash": meaningful_hash}
                        },
                    }
                }
            },
        )
        return resp["count"] > 0

    async def count_chunks(self, filters: MessageFilters | None = None) -> int:
        """Count chunk documents, optionally filtered."""
        clauses = _build_nested_filters(filters) if filters else []
        query = {"bool": {"filter": clauses}} if clauses else {"match_all": {}}
        resp = await self.client.count(index=self.index, body={"query": query})
        return resp["count"]

    async def list_chunks(
        self, request: ConversationChunkListRequest
    ) -> PaginatedConversationChunksResponse:
        """List chunk documents with filters and pagination."""
        clauses = _build_nested_filters(request.filters)
        query = {"bool": {"filter": clauses}} if clauses else {"match_all": {}}
        sort = _sort_clause(request.sort_by, request.sort_order) or [
            {"date": {"order": request.sort_order}}
        ]
        # count_resp = await self.client.count(index=self.index, body={"query": query})
        resp = await self.client.search(
            index=self.index,
            body={
                "query": query,
                "sort": sort,
                "from": request.offset,
                "size": request.limit,
            },
        )
        return _extract(
            resp,
            total=resp["hits"]["total"]["value"],
            page=request.page,
            limit=request.limit,
            return_messages=False,
        )

    async def get_chunk_context(
        self,
        chunk_id: str,
        limit: int,
        cursor: datetime | None,
        is_after: bool,
    ) -> list[ScoredConversationChunk]:
        """Get Chunks around a certain chunk."""
        chunk = await self.get_chunk_by_id(chunk_id)
        if chunk is None:
            raise ValueError(f"Chunk not found: {chunk_id}")

        pivot = cursor or chunk.date
        range_clause = (
            {"gt": pivot.isoformat()} if is_after else {"lt": pivot.isoformat()}
        )
        sort_order = "asc" if is_after else "desc"

        resp = await self.client.search(
            index=self.index,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"conversation_id": chunk.conversation_id}},
                            {"range": {"date": range_clause}},
                        ]
                    }
                },
                "sort": [{"date": {"order": sort_order}}],
                "size": limit,
            },
        )

        results = [_chunk_from_hit(hit) for hit in resp["hits"]["hits"]]
        return results if is_after else list(reversed(results))

    async def get_conversation_chunks(
        self, conversation_id: str, *, limit: int = 10
    ) -> list[ScoredConversationChunk]:
        """Get all chunks for a conversation sorted chronologically by date."""
        resp = await self.client.search(
            index=self.index,
            body={
                "query": {"term": {"conversation_id": conversation_id}},
                "sort": [{"date": {"order": "asc"}}],
                "size": limit,
            },
        )
        return [_chunk_from_hit(hit) for hit in resp["hits"]["hits"]]

    async def toggle_chunk_tag(
        self, chunk_id: str, tag: str, tag_type: ModelTagType
    ) -> ScoredConversationChunk | None:
        """Tag a chunk of messages with a positive or negative tag.

        If the tag already exists, it will be removed (toggled off).
        This is primarily to be used to train lightweight classifiers.
        """
        chunk = await self.get_chunk_by_id(chunk_id)
        if not chunk:
            return None

        is_pos = tag_type == ModelTagType.POSITIVE
        target_field = "tags" if is_pos else "negative_tags"
        other_field = "negative_tags" if is_pos else "tags"

        target_list: list[str] = getattr(chunk, target_field)
        other_list: list[str] = getattr(chunk, other_field)

        if tag in other_list:
            other_list.remove(tag)
            target_list.append(tag)
        elif tag in target_list:
            target_list.remove(tag)
        else:
            target_list.append(tag)

        # Using 'doc' for a partial update of just the tagging fields
        await self.client.update(
            index=self.index,
            id=chunk_id,
            body={
                "doc": {
                    "tags": chunk.tags,
                    "negative_tags": chunk.negative_tags,
                }
            },
            refresh=True,
        )

        return chunk

    async def search_text(
        self,
        request: TextSearchRequest,
    ) -> PaginatedConversationChunksResponse | PaginatedMessagesResponse:
        """BM25 search over message text and translation within chunks."""
        clauses = _build_nested_filters(request.filters)
        nested: dict = {
            "path": "messages",
            "query": {
                "multi_match": {
                    "query": request.query,
                    "fields": ["messages.text", "messages.translation"],
                }
            },
            "score_mode": "max",
        }
        if request.return_messages:
            nested["inner_hits"] = _inner_hits_clause()

        body: dict = {
            "query": {
                "bool": {
                    "must": [{"nested": nested}],
                    "filter": clauses,
                }
            },
            "from": request.offset,
            "size": request.limit,
        }
        sort = _sort_clause(request.sort_by, request.sort_order)
        if sort:
            body["sort"] = sort

        resp = await self.client.search(index=self.index, body=body)
        return _extract(
            resp,
            total=resp["hits"]["total"]["value"],
            page=request.page,
            limit=request.limit,
            return_messages=request.return_messages,
        )

    async def search_semantic(
        self, request: ConversationChunkSemanticSearchRequest
    ) -> PaginatedConversationChunksResponse:
        """KNN search over chunk embeddings, scored by cosine similarity."""
        clauses = _build_nested_filters(request.filters)
        knn = _knn_clause(
            embedding=request.embedding,
            limit=request.limit,
            num_candidates=request.num_candidates,
            min_similarity=request.min_similarity,
            filters=clauses,
        )
        resp = await self.client.search(
            index=self.index, body={"knn": knn, "size": request.limit}
        )
        total = resp["hits"]["total"]["value"]
        return _extract(
            resp,
            total=total,
            page=request.page,
            limit=request.limit,
            return_messages=False,
        )

    async def search_by_chunk_id(
        self, request: ConversationChunkByChunkIdRequest
    ) -> PaginatedConversationChunksResponse:
        """KNN search using an existing message's stored chunk embedding as the query vector."""
        embedding = await self.get_chunk_by_id(request.chunk_id)
        if embedding is None:
            raise ValueError(f"Chunk not found for ID: {request.chunk_id}")

        return await self.search_semantic(
            ConversationChunkSemanticSearchRequest(
                embedding=embedding,
                filters=request.filters,
                limit=request.limit,
                page=request.page,
                sort_by=request.sort_by,
                sort_order=request.sort_order,
                num_candidates=request.num_candidates,
                min_similarity=request.min_similarity,
            )
        )

    async def search_hybrid(
        self, request: ConversationChunkHybridSearchRequest
    ) -> PaginatedConversationChunksResponse:
        """Hybrid RRF search combining BM25 text and kNN chunk embedding similarity."""
        clauses = _build_nested_filters(request.filters)
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
                    "must": [
                        {
                            "nested": {
                                "path": "messages",
                                "query": {
                                    "multi_match": {
                                        "query": request.query,
                                        "fields": [
                                            "messages.text",
                                            "messages.translation",
                                        ],
                                    }
                                },
                                "score_mode": "max",
                            }
                        }
                    ],
                    "filter": clauses,
                }
            },
            "knn": knn,
            "rank": {
                "rrf": {"window_size": request.num_candidates, "rank_constant": 60}
            },
        }
        count_resp = await self.client.count(
            index=self.index, body={"query": body["query"]}
        )
        resp = await self.client.search(index=self.index, body=body)
        return _extract(
            resp,
            total=count_resp["count"],
            page=request.page,
            limit=request.limit,
            return_messages=False,
        )

    async def _send_batch(self, batch: list[ConversationChunk]) -> tuple[int, int]:
        """Internal helper to format and send a single batch to ES."""
        operations = []
        for chunk in batch:
            # Header line
            operations.append({"index": {"_index": self.index, "_id": str(chunk.id)}})
            # Data line
            operations.append(
                chunk.model_dump(exclude={"id"}, by_alias=False, mode="json")
            )

        resp = await self.client.bulk(
            operations=operations,
            refresh=False,  # Faster indexing; we'll refresh at the very end
            timeout=-1,  # Disable bulk timeout to allow large batches to complete
        )

        indexed = sum(
            1 for item in resp["items"] if item["index"]["status"] in (200, 201)
        )
        return indexed, len(resp["items"]) - indexed

    async def bulk_index(
        self, chunks: list[ConversationChunk], batch_size: int = 100
    ) -> tuple[int, int]:
        """Bulk index records with internal batching and a progress bar.

        Returns (total_indexed, total_failed).
        """
        total_indexed = 0
        total_failed = 0

        for i in tqdm(
            range(0, len(chunks), batch_size),
            desc=f"Indexing to {self.index}",
            unit="batch",
        ):
            batch = chunks[i : i + batch_size]
            indexed, failed = await self._send_batch(batch)
            total_indexed += indexed
            total_failed += failed

        # Refresh the index once at the end so data is immediately searchable
        await self.client.indices.refresh(index=self.index)

        return total_indexed, total_failed
