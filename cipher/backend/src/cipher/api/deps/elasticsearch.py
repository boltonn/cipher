"""FastAPI lifespan and dependencies for the Elasticsearch datastore."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from loguru import logger

from cipher.api.settings import Settings
from cipher.datastores.elasticsearch.client import get_async_client
from cipher.datastores.elasticsearch.repositories.message import (
    ElasticsearchMessageRepository,
)
from cipher.datastores.elasticsearch.repositories.text_chunk import (
    ElasticsearchTextChunkRepository,
)
from cipher.schemas.content.message import Message

settings = Settings()


@asynccontextmanager
async def elasticsearch_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager to initialize the Elasticsearch client.

    Stores a single AsyncElasticsearch client on app.state for the lifetime
    of the process. All requests share the client's internal connection pool
    rather than opening a new connection per request.
    """
    async with get_async_client(config=settings.elasticsearch) as client:
        app.state.es_client = client
        yield


async def get_message_repository(
    request: Request,
) -> AsyncGenerator[ElasticsearchMessageRepository, None]:
    """Dependency injector for ElasticsearchMessageRepository."""
    try:
        yield ElasticsearchMessageRepository(client=request.app.state.es_client)
    except AttributeError as exc:
        logger.exception(exc)
        raise HTTPException(
            status_code=503,
            detail="Elasticsearch client not initialized — is the lifespan registered?",
        ) from exc


MessageDatastoreDep = Annotated[
    ElasticsearchMessageRepository, Depends(get_message_repository)
]


async def get_text_chunk_repository(
    request: Request,
) -> AsyncGenerator[ElasticsearchTextChunkRepository, None]:
    """Dependency injector for ElasticsearchTextChunkRepository (unified document+email index)."""
    try:
        yield ElasticsearchTextChunkRepository(client=request.app.state.es_client)
    except AttributeError as exc:
        logger.exception(exc)
        raise HTTPException(
            status_code=503,
            detail="Elasticsearch client not initialized — is the lifespan registered?",
        ) from exc


TextChunkDatastoreDep = Annotated[
    ElasticsearchTextChunkRepository, Depends(get_text_chunk_repository)
]


__all__ = [
    "Message",
    "elasticsearch_lifespan",
    "get_message_repository",
    "MessageDatastoreDep",
    "get_text_chunk_repository",
    "TextChunkDatastoreDep",
]
