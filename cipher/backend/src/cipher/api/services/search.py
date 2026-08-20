"""Retrieval glue shared by the `/search` router and the chat agent's citation tool."""

from clir.api.deps import AsyncTextEmbeddingModel

from cipher.datastores.elasticsearch.repositories.text_chunk import (
    ElasticsearchTextChunkRepository,
    ScoredTextChunk,
)
from cipher.datastores.elasticsearch.utils import PaginatedResponse
from cipher.schemas.search import ChunkHybridSearchRequest, ChunkTextSearchRequest


async def search_chunks(
    *,
    params: ChunkTextSearchRequest,
    datastore: ElasticsearchTextChunkRepository,
    embedding_model: AsyncTextEmbeddingModel,
) -> PaginatedResponse[ScoredTextChunk]:
    """Embed `params.query` and run hybrid RRF search across documents and emails.

    Raises `RuntimeError` if the embedding model is unavailable.
    """
    embedding = await embedding_model.infer(text=params.query, task="retrieval", prompt="Query: ")
    if embedding is None:
        raise RuntimeError("Embedding model unavailable")

    request = ChunkHybridSearchRequest.model_validate(
        {**params.model_dump(exclude_none=True), "embedding": embedding}
    )
    return await datastore.search_hybrid(request=request)
