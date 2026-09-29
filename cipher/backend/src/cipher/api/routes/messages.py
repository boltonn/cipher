"""Messages API router — conversation chunk retrieval and search."""

from typing import Annotated

from clir.api.deps import TextEmbeddingModelDep, model_lifespan
from fastapi import APIRouter, Body, Depends, HTTPException, Path

from cipher.api.deps.elasticsearch import MessageDatastoreDep
from cipher.schemas._base.common import TagRequest, TranslationUpdate
from cipher.schemas.content.message import (
    BaseMessageTextSearchParameters,
    ChunkContextRequestParams,
    ConversationChunkByChunkIdRequest,
    ConversationChunkHybridSearchRequest,
    ConversationChunkSemanticSearchRequest,
    Message,
    PaginatedConversationChunksResponse,
    ScoredConversationChunk,
    TextSearchRequest,
)

router = APIRouter(
    prefix="/messages",
    tags=["messages"],
    responses={418: {"description": "I'm a teapot"}},
    lifespan=model_lifespan,
)


@router.get(
    "/{id}",
    summary="Get a message by its source message_id",
    response_model=Message,
)
async def get_message_by_id(
    id: str,
    datastore: MessageDatastoreDep,
):
    """Get a single message by its source message_id (e.g. 'sms_42')."""
    message = await datastore.get_message_by_id(message_id=id)
    if message is None:
        raise HTTPException(status_code=404, detail=f"Message not found: {id}")
    return message


@router.get(
    "/chunks/{id}",
    summary="Get a conversation chunk by its ID",
    response_model=ScoredConversationChunk,
)
async def get_chunk_by_id(
    id: str,
    datastore: MessageDatastoreDep,
):
    """Get a single conversation chunk by its UUID."""
    chunk = await datastore.get_chunk_by_id(chunk_id=str(id))
    if chunk is None:
        raise HTTPException(status_code=404, detail=f"Chunk not found: {id}")
    return chunk


@router.get(
    "/chunks/{id}/context",
    summary="Get chunks before or after a given chunk in its conversation",
    response_model=list[ScoredConversationChunk],
)
async def get_chunk_context(
    id: str,
    datastore: MessageDatastoreDep,
    params: Annotated[ChunkContextRequestParams, Depends()],
):
    """Get chunks context."""
    return await datastore.get_chunk_context(
        chunk_id=id,
        limit=params.limit,
        cursor=params.cursor,
        is_after=params.is_after,
    )


@router.get(
    "/conversations/{id}",
    summary="Get all chunks for a conversation",
    response_model=list[ScoredConversationChunk],
)
async def get_conversation_chunks(
    id: str,
    datastore: MessageDatastoreDep,
    limit: int = 10,
):
    """Get all chunks for a conversation sorted chronologically."""
    return await datastore.get_conversation_chunks(conversation_id=id, limit=limit)


@router.patch(
    "/chunks/{id}/tag",
    summary="Toggle a positive or negative tag on a chunk",
    response_model=ScoredConversationChunk,  # Returns updated chunk for UI sync
)
async def toggle_chunk_tag(
    id: Annotated[str, Path(description="The ID of the conversation chunk")],
    tag_data: Annotated[TagRequest, Body(...)],
    datastore: MessageDatastoreDep,
):
    """Toggles a tag on a chunk.

    If 'positive', it updates the 'tags' list.
    If 'negative', it updates the 'negative_tags' list.
    """
    # We pass the type to the datastore to let it decide which column/field to update
    updated_chunk = await datastore.toggle_chunk_tag(
        chunk_id=str(id), tag=tag_data.tag, tag_type=tag_data.type
    )

    if updated_chunk is None:
        raise HTTPException(status_code=404, detail=f"Chunk not found: {id}")

    return updated_chunk


@router.post(
    "/search/text",
    summary="BM25 full-text search over message content",
    response_model_by_alias=True,
)
async def search_text(
    params: TextSearchRequest,
    datastore: MessageDatastoreDep,
):
    """Search conversation chunks by keyword across message text and translations."""
    return await datastore.search_text(request=params)


@router.post(
    "/search/semantic",
    summary="Semantic search using a natural language query string",
    response_model_by_alias=True,
)
async def search_semantic(
    params: BaseMessageTextSearchParameters,
    datastore: MessageDatastoreDep,
    model: TextEmbeddingModelDep,
):
    """Embed a query string and perform kNN search — no pre-computed embedding needed."""
    embedding = await model.infer(text=params.query, task="retrieval")

    if embedding is None:
        raise HTTPException(status_code=503, detail="Embedding model unavailable")

    return await datastore.search_semantic(
        request=ConversationChunkSemanticSearchRequest.model_validate(
            {**params.model_dump(exclude_none=True), "embedding": embedding}
        )
    )


@router.post(
    "/search/hybrid",
    summary="Hybrid search using a natural language query string",
    response_model=PaginatedConversationChunksResponse,
    response_model_by_alias=True,
)
async def search_hybrid_by_query(
    params: BaseMessageTextSearchParameters,
    datastore: MessageDatastoreDep,
    model: TextEmbeddingModelDep,
):
    """Embed a query string and run hybrid RRF search — no pre-computed embedding needed."""
    embedding = await model.infer(text=params.query, task="retrieval")
    if embedding is None:
        raise HTTPException(status_code=503, detail="Embedding model unavailable")

    return await datastore.search_hybrid(
        request=ConversationChunkHybridSearchRequest.model_validate(
            {**params.model_dump(exclude_none=True), "embedding": embedding}
        )
    )


@router.get(
    "/search/{chunk_id}",
    summary="Find similar chunks using an existing chunk's embedding",
    response_model=PaginatedConversationChunksResponse,
    response_model_by_alias=True,
)
async def search_by_chunk_id(
    chunk_id: str,
    params: Annotated[ConversationChunkByChunkIdRequest, Depends()],
    datastore: MessageDatastoreDep,
):
    """Find conversation chunks semantically similar to the given chunk."""
    embedding = await datastore.get_chunk_embedding_by_id(chunk_id=chunk_id)
    if embedding is None:
        raise HTTPException(status_code=404, detail=f"Chunk not found: {chunk_id}")

    return await datastore.search_semantic(
        request=ConversationChunkSemanticSearchRequest.model_validate(
            {**params.model_dump(exclude_none=True), "embedding": embedding}
        )
    )


@router.patch(
    "/{id}/translate",
    summary="Set the translation for a message",
    response_model=bool,
)
async def translate_message(
    id: Annotated[str, Path(description="The source message UUID")],
    payload: Annotated[TranslationUpdate, Body(...)],
    datastore: MessageDatastoreDep,
):
    """Update the translation field of a message by its source message_id."""
    updated = await datastore.translate_message(
        message_id=id, translation=payload.translation
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Message not found: {id}")
    return updated


@router.delete(
    "/chunks/{id}",
    summary="Delete a conversation chunk",
    response_model=bool,
)
async def delete_chunk(
    id: str,
    datastore: MessageDatastoreDep,
):
    """Delete a conversation chunk and all its messages by chunk UUID."""
    deleted = await datastore.delete_chunk(chunk_id=str(id))
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Chunk not found: {id}")
    return deleted
