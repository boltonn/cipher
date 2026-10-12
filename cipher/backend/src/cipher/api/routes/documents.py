"""Documents API router — search over the `document`-typed slice of the unified text_chunks index."""

from clir.api.deps import TextEmbeddingModelDep
from fastapi import APIRouter, HTTPException

from cipher.api.deps.access import DatasetAccess, DatasetAccessDep
from cipher.api.deps.elasticsearch import TextChunkDatastoreDep
from cipher.schemas.content.document import ScoredDocumentTextChunk
from cipher.schemas.content.search import (
    ChunkFilters,
    ChunkHybridSearchRequest,
    ChunkSemanticSearchRequest,
    ChunkTextSearchRequest,
)

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    responses={418: {"description": "I'm a teapot"}},
)


def _scoped_to_documents(filters: ChunkFilters, access: DatasetAccess) -> ChunkFilters:
    """Force filetype_group=document regardless of what the caller passed -- this router only ever searches documents."""
    return access.scoped(filters).model_copy(update={"filetype_group": "document"})


@router.get(
    "/chunks/{id}",
    summary="Get a document chunk by its ID",
    response_model=ScoredDocumentTextChunk,
)
async def get_chunk_by_id(id: str, access: DatasetAccessDep, datastore: TextChunkDatastoreDep):
    """Get a single document chunk by its Elasticsearch document ID."""
    chunk = await datastore.get_by_id(id)
    if chunk is None or chunk.filetype_group != "document" or not access.allows(chunk.dataset_id):
        raise HTTPException(status_code=404, detail=f"Document chunk not found: {id}")
    return chunk


@router.post(
    "/search/text",
    summary="BM25 full-text search over document content",
    response_model_by_alias=True,
)
async def search_text(params: ChunkTextSearchRequest, access: DatasetAccessDep, datastore: TextChunkDatastoreDep):
    """Search document chunks by keyword."""
    params.filters = _scoped_to_documents(params.filters, access)
    return await datastore.search_text(request=params)


@router.post(
    "/search/semantic",
    summary="Semantic search using a natural language query string",
    response_model_by_alias=True,
)
async def search_semantic(
    params: ChunkTextSearchRequest,
    access: DatasetAccessDep,
    datastore: TextChunkDatastoreDep,
    model: TextEmbeddingModelDep,
):
    """Embed a query string and perform kNN search over document chunks -- no pre-computed embedding needed."""
    embedding = await model.infer(text=params.query, task="retrieval")
    if embedding is None:
        raise HTTPException(status_code=503, detail="Embedding model unavailable")

    request = ChunkSemanticSearchRequest.model_validate(
        {**params.model_dump(exclude={"query"}, exclude_none=True), "embedding": embedding}
    )
    request.filters = _scoped_to_documents(request.filters, access)
    return await datastore.search_semantic(request=request)


@router.post(
    "/search/hybrid",
    summary="Hybrid search using a natural language query string",
    response_model_by_alias=True,
)
async def search_hybrid(
    params: ChunkTextSearchRequest,
    access: DatasetAccessDep,
    datastore: TextChunkDatastoreDep,
    model: TextEmbeddingModelDep,
):
    """Embed a query string and run hybrid RRF search over document chunks -- no pre-computed embedding needed."""
    embedding = await model.infer(text=params.query, task="retrieval")
    if embedding is None:
        raise HTTPException(status_code=503, detail="Embedding model unavailable")

    request = ChunkHybridSearchRequest.model_validate({**params.model_dump(exclude_none=True), "embedding": embedding})
    request.filters = _scoped_to_documents(request.filters, access)
    return await datastore.search_hybrid(request=request)


@router.delete(
    "/chunks/{id}",
    summary="Delete a document chunk",
    response_model=bool,
)
async def delete_chunk(id: str, access: DatasetAccessDep, datastore: TextChunkDatastoreDep):
    """Delete a document chunk by its Elasticsearch document ID."""
    chunk = await datastore.get_by_id(id)
    if chunk is not None:
        access.require(chunk.dataset_id)
    deleted = await datastore.delete(id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Document chunk not found: {id}")
    return deleted
