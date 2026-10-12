"""FastAPI lifespan and dependencies for the Elasticsearch datastore."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from loguru import logger

from cipher.api.settings import Settings
from cipher.datastores.base.retrieval import ChunkRetrievalRepository
from cipher.datastores.elasticsearch.client import get_async_client
from cipher.datastores.elasticsearch.repositories.message import (
    ElasticsearchMessageRepository,
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


MessageDatastoreDep = Annotated[ElasticsearchMessageRepository, Depends(get_message_repository)]


async def get_text_chunk_repository(request: Request):
    """Chunk-search datastore for the configured `RETRIEVAL__BACKEND`.

    Both implementations satisfy `ChunkRetrievalRepository` (`search`,
    `search_text`/`search_semantic`/`search_hybrid` shims, etc.) so the `/search`
    routes and the chat agent are backend-agnostic. Both also need a Postgres
    session: entity/graph data always lives there regardless of which store
    answers the text/vector query -- the elasticsearch adapter resolves entity
    and graph_expand filters live via `mention.chunk_id` into an ES `terms`
    filter, rather than denormalizing them onto the chunk doc.
    """
    from cipher.api.deps.postgres import get_session
    from cipher.api.settings import RetrievalBackend, Settings
    from cipher.datastores.postgres.repositories.entity_relationship import (
        PostgresGraphRepository,
    )

    cfg = Settings().retrieval
    async with get_session() as session:
        graph_repo = PostgresGraphRepository(session=session)
        if cfg.backend == RetrievalBackend.POSTGRES:
            from cipher.datastores.postgres.repositories.chunk_retrieval import (
                PostgresChunkRetrievalRepository,
            )

            yield PostgresChunkRetrievalRepository(
                session=session,
                text_ranker=cfg.text_ranker.value,
                graph_repo=graph_repo,
                graph_expand_entity_cap=cfg.graph_expand_entity_cap,
            )
            return

        try:
            client = request.app.state.es_client
        except AttributeError as exc:
            logger.exception(exc)
            raise HTTPException(
                status_code=503,
                detail="Elasticsearch client not initialized — is the lifespan registered?",
            ) from exc
        from cipher.datastores.elasticsearch.repositories.chunk_retrieval import (
            ElasticsearchChunkRetrievalRepository,
        )

        yield ElasticsearchChunkRetrievalRepository(
            client=client,
            session=session,
            graph_repo=graph_repo,
            graph_expand_entity_cap=cfg.graph_expand_entity_cap,
        )


TextChunkDatastoreDep = Annotated[ChunkRetrievalRepository, Depends(get_text_chunk_repository)]


__all__ = [
    "Message",
    "elasticsearch_lifespan",
    "get_message_repository",
    "MessageDatastoreDep",
    "get_text_chunk_repository",
    "TextChunkDatastoreDep",
]
