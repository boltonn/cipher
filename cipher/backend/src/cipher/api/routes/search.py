"""Unified search API router — BM25/semantic/hybrid search across documents and emails together.

Both content types live in the same `text_chunks` Elasticsearch index, so
this is a single query with a real server-side `total`/`has_more` over the
combined result set -- unlike `/documents/search/*` and `/emails/search/*`,
which force `filetype_group` and only ever see one type's slice, so paging
either of them independently can't tell a caller when *all* matching content
(documents and emails together) has been exhausted.
"""

from clir.api.deps import TextEmbeddingModelDep
from fastapi import APIRouter, HTTPException

from cipher.api.deps.elasticsearch import TextChunkDatastoreDep
from cipher.schemas.search import (
    ChunkHybridSearchRequest,
    ChunkSemanticSearchRequest,
    ChunkTextSearchRequest,
)

router = APIRouter(
    prefix="/search",
    tags=["search"],
    responses={418: {"description": "I'm a teapot"}},
)


@router.post(
    "/text",
    summary="BM25 full-text search across documents and emails",
    response_model_by_alias=True,
)
async def search_text(params: ChunkTextSearchRequest, datastore: TextChunkDatastoreDep):
    """Search chunk text/title by keyword.

    BM25 only ever matches chunks containing a query term, so `has_more`
    naturally goes false once nothing left matches -- no similarity
    threshold needed the way semantic/hybrid search requires one.
    """
    return await datastore.search_text(request=params)


@router.post(
    "/semantic",
    summary="Semantic search using a natural language query string, across documents and emails",
    response_model_by_alias=True,
)
async def search_semantic(
    params: ChunkTextSearchRequest,
    datastore: TextChunkDatastoreDep,
    model: TextEmbeddingModelDep,
):
    """Embed a query string and perform kNN search -- no pre-computed embedding needed.

    Set `min_similarity` on the request to give pagination a real stopping
    point: kNN otherwise always returns its requested candidate count
    regardless of relevance, so without a threshold `has_more` would stay
    true well past the point where results still match the query.
    """
    embedding = await model.infer(text=params.query, task="retrieval", prompt="Query: ")
    if embedding is None:
        raise HTTPException(status_code=503, detail="Embedding model unavailable")

    request = ChunkSemanticSearchRequest.model_validate(
        {**params.model_dump(exclude={"query"}, exclude_none=True), "embedding": embedding}
    )
    return await datastore.search_semantic(request=request)


@router.post(
    "/hybrid",
    summary="Hybrid search using a natural language query string, across documents and emails",
    response_model_by_alias=True,
)
async def search_hybrid(
    params: ChunkTextSearchRequest,
    datastore: TextChunkDatastoreDep,
    model: TextEmbeddingModelDep,
):
    """Embed a query string and run hybrid RRF search -- no pre-computed embedding needed."""
    embedding = await model.infer(text=params.query, task="retrieval", prompt="Query: ")
    if embedding is None:
        raise HTTPException(status_code=503, detail="Embedding model unavailable")

    request = ChunkHybridSearchRequest.model_validate(
        {**params.model_dump(exclude_none=True), "embedding": embedding}
    )
    return await datastore.search_hybrid(request=request)
