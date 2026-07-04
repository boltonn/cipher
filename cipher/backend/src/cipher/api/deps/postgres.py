from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, Form
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from cipher.api.settings import Settings
from cipher.datastores.postgres.repositories.comment import PostgresCommentRepository
from cipher.datastores.postgres.repositories.dataset import PostgresDatasetRepository
from cipher.datastores.postgres.repositories.enrichment import (
    PostgresEnrichmentRepository,
)
from cipher.datastores.postgres.repositories.face import PostgresFaceRepository
from cipher.datastores.postgres.repositories.face_match import PostgresFaceMatchRepository
from cipher.datastores.postgres.repositories.file import PostgresFileRepository
from cipher.datastores.postgres.repositories.image import PostgresImageRepository
from cipher.datastores.postgres.repositories.person import PostgresPersonRepository
from cipher.datastores.postgres.repositories.user import PostgresUserRepository
from cipher.datastores.postgres.tables.base import Base
from cipher.schemas.comment import Comment
from cipher.schemas.common import SortOrder
from cipher.schemas.dataset import Dataset
from cipher.schemas.enrichment import Enrichment
from cipher.schemas.face import Face, FaceSimilaritySearchParameters, FaceSortField
from cipher.schemas.face_match import FaceMatch
from cipher.schemas.file import File
from cipher.schemas.image import Image, ImageSimilaritySearchParameters, ImageSortField
from cipher.schemas.person import Person
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
    """Provide a session per request using the cached engine.

    expire_on_commit=False: repository methods that commit and then return
    the just-written ORM object (via .returning() or similar) would otherwise
    trigger a lazy-load on attribute access post-commit, which fails outside
    an awaited context (MissingGreenlet).
    """
    async with AsyncSession(get_async_engine_from_settings(), expire_on_commit=False) as session:
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


async def get_face_repository() -> AsyncGenerator[PostgresFaceRepository, None]:
    """Dependency injector for PostgresFaceRepository."""
    async with get_session() as session:
        yield PostgresFaceRepository(session=session)


async def get_person_repository() -> AsyncGenerator[PostgresPersonRepository, None]:
    """Dependency injector for PostgresPersonRepository."""
    async with get_session() as session:
        yield PostgresPersonRepository(session=session)


async def get_comment_repository() -> AsyncGenerator[PostgresCommentRepository, None]:
    """Dependency injector for PostgresCommentRepository."""
    async with get_session() as session:
        yield PostgresCommentRepository(session=session)


async def get_face_match_repository() -> AsyncGenerator[PostgresFaceMatchRepository, None]:
    """Dependency injector for PostgresFaceMatchRepository."""
    async with get_session() as session:
        yield PostgresFaceMatchRepository(session=session)


DatasetDatastoreDep = Annotated[
    PostgresDatasetRepository, Depends(get_dataset_repository)
]
EnrichmentDatastoreDep = Annotated[
    PostgresEnrichmentRepository, Depends(get_enrichment_repository)
]
FileDatastoreDep = Annotated[PostgresFileRepository, Depends(get_file_repository)]
ImageDatastoreDep = Annotated[PostgresImageRepository, Depends(get_image_repository)]
UserDatastoreDep = Annotated[PostgresUserRepository, Depends(get_user_repository)]
FaceDatastoreDep = Annotated[PostgresFaceRepository, Depends(get_face_repository)]
PersonDatastoreDep = Annotated[
    PostgresPersonRepository, Depends(get_person_repository)
]
CommentDatastoreDep = Annotated[
    PostgresCommentRepository, Depends(get_comment_repository)
]
FaceMatchDatastoreDep = Annotated[
    PostgresFaceMatchRepository, Depends(get_face_match_repository)
]


def image_similarity_params_form(
    page: Annotated[int, Form(ge=1)],
    limit: Annotated[int, Form(ge=1, le=100)] = 10,
    sort_by: Annotated[str, Form()] = ImageSortField.SIMILARITY,
    sort_order: Annotated[SortOrder, Form()] = SortOrder.DESC,
    min_similarity: Annotated[float | None, Form(ge=0.0, le=1.0)] = None,
    date_from: Annotated[str | None, Form()] = None,
    date_to: Annotated[str | None, Form()] = None,
    datasets: Annotated[list[str] | None, Form()] = None,
    filetypes: Annotated[list[str] | None, Form()] = None,
    tags: Annotated[list[str] | None, Form()] = None,
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
            "date_from": date_from,
            "date_to": date_to,
            "datasets": datasets,
            "filetypes": filetypes,
            "tags": tags,
        }
    )


ImageSimilaritySearchFormParametersDep = Annotated[
    ImageSimilaritySearchParameters, Depends(image_similarity_params_form)
]


def face_similarity_params_form(
    page: Annotated[int, Form(ge=1)],
    limit: Annotated[int, Form(ge=1, le=100)] = 10,
    sort_by: Annotated[str, Form()] = FaceSortField.SIMILARITY,
    sort_order: Annotated[SortOrder, Form()] = SortOrder.DESC,
    min_similarity: Annotated[float | None, Form(ge=0.0, le=1.0)] = None,
):
    """Dependency injector for FaceSimilaritySearchParameters from form data.

    This tricks FastAPI into accepting form data for complex objects where you
    are using FastAPI's Form() function for individual fields but still want to
    receive a single object in your route function.
    """
    return FaceSimilaritySearchParameters.model_validate(
        {
            "limit": limit,
            "page": page,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "min_similarity": min_similarity,
        }
    )


FaceSimilaritySearchFormParametersDep = Annotated[
    FaceSimilaritySearchParameters, Depends(face_similarity_params_form)
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
    "Face",
    "FaceMatch",
    "Person",
    "Comment",
    "get_session",
    "get_async_engine_from_settings",
    "get_dataset_repository",
    "get_enrichment_repository",
    "get_file_repository",
    "get_image_repository",
    "get_face_repository",
    "get_person_repository",
    "get_comment_repository",
    "get_face_match_repository",
    "DatasetDatastoreDep",
    "EnrichmentDatastoreDep",
    "FileDatastoreDep",
    "ImageDatastoreDep",
    "ImageSimilaritySearchFormParametersDep",
    "FaceDatastoreDep",
    "PersonDatastoreDep",
    "CommentDatastoreDep",
    "FaceMatchDatastoreDep",
    "FaceSimilaritySearchFormParametersDep",
    "postgres_lifespan",
]
