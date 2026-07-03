from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, Form
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from cipher.api.settings import Settings
from cipher.datastores.postgres.repositories.dataset import PostgresDatasetRepository
from cipher.datastores.postgres.repositories.enrichment import (
    PostgresEnrichmentRepository,
)
from cipher.datastores.postgres.repositories.file import PostgresFileRepository
from cipher.datastores.postgres.repositories.image import PostgresImageRepository
from cipher.datastores.postgres.repositories.user import PostgresUserRepository
from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.common import SortOrder
from cipher.schemas.dataset import Dataset
from cipher.schemas.enrichment import Enrichment
from cipher.schemas.file import File
from cipher.schemas.image import Image, ImageSimilaritySearchParameters, ImageSortField
from cipher.schemas.user import User, UserDatasetAccess

settings = Settings()


@lru_cache(maxsize=1)
def get_async_engine_from_settings() -> AsyncEngine:
    """Return a cached AsyncEngine; called once per process."""
    database_url = (
        f"postgresql+asyncpg://{settings.postgres.username}:{settings.postgres.password}"
        f"@{settings.postgres.host}:{settings.postgres.port}/{settings.postgres.database}"
    )
    engine = create_async_engine(
        database_url,
        pool_size=settings.postgres.pool_size,
        max_overflow=settings.postgres.max_overflow,
    )
    return engine


@asynccontextmanager
async def get_session():
    """Provide a session per request using the cached engine."""
    async with AsyncSession(get_async_engine_from_settings()) as session:
        yield session


async def init_db_from_settings():
    """Initialize the database by creating all tables."""
    async with get_async_engine_from_settings().begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


async def get_dataset_repository() -> AsyncGenerator[PostgresDatasetRepository, None]:
    """Dependency injector for PostgresDatasetRepository."""
    async with get_session() as session:
        yield PostgresDatasetRepository(session=session)


async def get_enrichment_repository() -> AsyncGenerator[
    PostgresEnrichmentRepository, None
]:
    """Dependency injector for PostgresEnrichmentRepository."""
    async with get_session() as session:
        yield PostgresEnrichmentRepository(session=session)


async def get_file_repository() -> AsyncGenerator[PostgresFileRepository, None]:
    """Dependency injector for PostgresFileRepository."""
    async with get_session() as session:
        yield PostgresFileRepository(session=session)


async def get_image_repository() -> AsyncGenerator[PostgresImageRepository, None]:
    """Dependency injector for PostgresImageRepository."""
    async with get_session() as session:
        yield PostgresImageRepository(session=session)


async def get_user_repository() -> AsyncGenerator[PostgresUserRepository, None]:
    """Dependency injector for PostgresUserRepository."""
    async with get_session() as session:
        yield PostgresUserRepository(session=session)


DatasetDatastoreDep = Annotated[
    PostgresDatasetRepository, Depends(get_dataset_repository)
]
EnrichmentDatastoreDep = Annotated[
    PostgresEnrichmentRepository, Depends(get_enrichment_repository)
]
FileDatastoreDep = Annotated[PostgresFileRepository, Depends(get_file_repository)]
ImageDatastoreDep = Annotated[PostgresImageRepository, Depends(get_image_repository)]
UserDatastoreDep = Annotated[PostgresUserRepository, Depends(get_user_repository)]


def image_similarity_params_form(
    page: Annotated[int, Form(ge=1)],
    limit: Annotated[int, Form(ge=1, le=100)] = 10,
    sort_by: Annotated[str, Form()] = ImageSortField.SIMILARITY,
    sort_order: Annotated[SortOrder, Form()] = SortOrder.DESC,
    min_similarity: Annotated[float | None, Form(ge=0.0, le=1.0)] = None,
):
    """Dependency injector for ImageSimilaritySearchParameters from form data.

    This tricks FastAPI into accepting form data for complex objects where you
    are using FastAPI's Form() function for individual fields but still want to
    receive a single object in your route function.
    """
    return ImageSimilaritySearchParameters.model_validate(
        {
            "limit": limit,
            "page": page,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "min_similarity": min_similarity,
        }
    )


ImageSimilaritySearchFormParametersDep = Annotated[
    ImageSimilaritySearchParameters, Depends(image_similarity_params_form)
]


@asynccontextmanager
async def postgres_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager to initialize the Postgres database."""
    await init_db_from_settings()
    yield


__all__ = [
    "User",
    "UserDatasetAccess",
    "Dataset",
    "File",
    "Image",
    "Enrichment",
    "get_session",
    "get_async_engine_from_settings",
    "get_dataset_repository",
    "get_enrichment_repository",
    "get_file_repository",
    "get_image_repository",
    "DatasetDatastoreDep",
    "EnrichmentDatastoreDep",
    "FileDatastoreDep",
    "ImageDatastoreDep",
    "ImageSimilaritySearchFormParametersDep",
    "postgres_lifespan",
]
