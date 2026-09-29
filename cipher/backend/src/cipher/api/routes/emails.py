from clir.api.deps import TextEmbeddingModelDep
from fastapi import APIRouter, HTTPException, UploadFile
from pyparse.parsers.email import EmlParser

from cipher.api.deps.elasticsearch import TextChunkDatastoreDep
from cipher.schemas.content.email import ScoredEmailTextChunk
from cipher.schemas.content.search import (
    ChunkFilters,
    ChunkHybridSearchRequest,
    ChunkSemanticSearchRequest,
    ChunkTextSearchRequest,
)

router = APIRouter(
    prefix="/emails",
    tags=["emails"],
    responses={418: {"description": "I'm a teapot"}},
)


def _scoped_to_emails(filters: ChunkFilters) -> ChunkFilters:
    """Force filetype_group=email regardless of what the caller passed -- this router only ever searches emails."""
    return filters.model_copy(update={"filetype_group": "email"})


@router.post(
    "/parse",
    summary="Parse an email file",
)
async def parse_email(
    file: UploadFile,
):
    """Parse an email file and return its structured representation for display."""
    email_bytes = await file.read()
    parser = EmlParser()
    email = parser.parse(email_bytes)
    return email


@router.get(
    "/chunks/{id}",
    summary="Get an email chunk by its ID",
    response_model=ScoredEmailTextChunk,
)
async def get_chunk_by_id(id: str, datastore: TextChunkDatastoreDep):
    """Get a single email chunk by its Elasticsearch document ID."""
    chunk = await datastore.get_by_id(id)
    if chunk is None or chunk.filetype_group != "email":
        raise HTTPException(status_code=404, detail=f"Email chunk not found: {id}")
    return chunk


@router.post(
    "/search/text",
    summary="BM25 full-text search over email content",
    response_model_by_alias=True,
)
async def search_text(params: ChunkTextSearchRequest, datastore: TextChunkDatastoreDep):
    """Search email chunks by keyword."""
    params.filters = _scoped_to_emails(params.filters)
    return await datastore.search_text(request=params)


@router.post(
    "/search/semantic",
    summary="Semantic search using a natural language query string",
    response_model_by_alias=True,
)
async def search_semantic(
    params: ChunkTextSearchRequest,
    datastore: TextChunkDatastoreDep,
    model: TextEmbeddingModelDep,
):
    """Embed a query string and perform kNN search over email chunks -- no pre-computed embedding needed."""
    embedding = await model.infer(text=params.query, task="retrieval")
    if embedding is None:
        raise HTTPException(status_code=503, detail="Embedding model unavailable")

    request = ChunkSemanticSearchRequest.model_validate(
        {**params.model_dump(exclude={"query"}, exclude_none=True), "embedding": embedding}
    )
    request.filters = _scoped_to_emails(request.filters)
    return await datastore.search_semantic(request=request)


@router.post(
    "/search/hybrid",
    summary="Hybrid search using a natural language query string",
    response_model_by_alias=True,
)
async def search_hybrid(
    params: ChunkTextSearchRequest,
    datastore: TextChunkDatastoreDep,
    model: TextEmbeddingModelDep,
):
    """Embed a query string and run hybrid RRF search over email chunks -- no pre-computed embedding needed."""
    embedding = await model.infer(text=params.query, task="retrieval")
    if embedding is None:
        raise HTTPException(status_code=503, detail="Embedding model unavailable")

    request = ChunkHybridSearchRequest.model_validate(
        {**params.model_dump(exclude_none=True), "embedding": embedding}
    )
    request.filters = _scoped_to_emails(request.filters)
    return await datastore.search_hybrid(request=request)


@router.delete(
    "/chunks/{id}",
    summary="Delete an email chunk",
    response_model=bool,
)
async def delete_chunk(id: str, datastore: TextChunkDatastoreDep):
    """Delete an email chunk by its Elasticsearch document ID."""
    deleted = await datastore.delete(id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Email chunk not found: {id}")
    return deleted
