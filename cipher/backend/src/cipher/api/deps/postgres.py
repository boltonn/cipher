from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, Form
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from cipher.api.settings import Settings, TextRanker
from cipher.datastores.postgres.repositories.comment import PostgresCommentRepository
from cipher.datastores.postgres.repositories.database_metrics import PostgresDatabaseMetricsRepository
from cipher.datastores.postgres.repositories.dataset import PostgresDatasetRepository
from cipher.datastores.postgres.repositories.enrichment import (
    PostgresEnrichmentRepository,
)
from cipher.datastores.postgres.repositories.enrichment_run import (
    PostgresEnrichmentRunRepository,
)
from cipher.datastores.postgres.repositories.entity import PostgresEntityRepository
from cipher.datastores.postgres.repositories.entity_match import PostgresEntityMatchRepository
from cipher.datastores.postgres.repositories.entity_relationship import PostgresGraphRepository
from cipher.datastores.postgres.repositories.entity_relationship_candidate import (
    PostgresRelationshipCandidateRepository,
)
from cipher.datastores.postgres.repositories.event import PostgresEventRepository
from cipher.datastores.postgres.repositories.extracted_text import PostgresExtractedTextRepository
from cipher.datastores.postgres.repositories.face import PostgresFaceRepository
from cipher.datastores.postgres.repositories.face_match import PostgresFaceMatchRepository
from cipher.datastores.postgres.repositories.file import PostgresFileRepository
from cipher.datastores.postgres.repositories.image import PostgresImageRepository
from cipher.datastores.postgres.repositories.location import PostgresLocationRepository
from cipher.datastores.postgres.repositories.mention import PostgresMentionRepository
from cipher.datastores.postgres.repositories.person import PostgresPersonRepository
from cipher.datastores.postgres.repositories.tag import PostgresTagRepository
from cipher.datastores.postgres.repositories.user import PostgresUserRepository
from cipher.datastores.postgres.tables.base import Base
from cipher.schemas._base.common import SortOrder
from cipher.schemas.content.image import Image, ImageSimilaritySearchParameters, ImageSortField
from cipher.schemas.identity.face import Face, FaceSimilaritySearchParameters, FaceSortField
from cipher.schemas.identity.face_match import FaceMatch
from cipher.schemas.identity.person import Person
from cipher.schemas.ingestion.dataset import Dataset
from cipher.schemas.ingestion.enrichment import Enrichment
from cipher.schemas.ingestion.file import File
from cipher.schemas.ingestion.user import User, UserDatasetAccess
from cipher.schemas.interaction.comment import Comment

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
        pool_pre_ping=True,
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


# The Postgres extension each keyword ranker needs; `core` needs none.
_RANKER_EXTENSION: dict[TextRanker, str] = {
    TextRanker.BIGM: "pg_bigm",
    TextRanker.PGROONGA: "pgroonga",
    TextRanker.PG_SEARCH: "pg_search",
}


async def init_db_from_settings():
    """Create all tables and the extensions the running configuration needs.

    The core extensions are required. The one extra extension for the configured
    keyword ranker (`RETRIEVAL__TEXT_RANKER`) is *attempted*: if its package
    isn't installed the retrieval layer downgrades one rung
    (`_effective_ranker`), so it's logged, not fatal. `core` needs nothing extra
    and is always silent. See docs/postgres-extensions.md.
    """
    ranker_ext = _RANKER_EXTENSION.get(settings.retrieval.text_ranker)
    async with get_async_engine_from_settings().begin() as conn:
        for ext in ("vector", "pg_trgm", "postgis", "unaccent"):
            await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
        if ranker_ext is not None:
            try:
                # SAVEPOINT: a missing extension aborts its statement, and in
                # Postgres that poisons the whole transaction ("current
                # transaction is aborted") -- isolate it so `create_all` still runs.
                async with conn.begin_nested():
                    await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ranker_ext}"))
            except Exception as exc:  # noqa: BLE001 -- package may not be installed; retrieval downgrades
                logger.warning(
                    f"Keyword ranker {settings.retrieval.text_ranker.value!r} needs Postgres extension "
                    f"{ranker_ext!r}, which is unavailable ({exc.__class__.__name__}); retrieval will "
                    f"downgrade one rung. See docs/postgres-extensions.md."
                )
        await conn.run_sync(Base.metadata.create_all)


async def get_dataset_repository() -> AsyncGenerator[PostgresDatasetRepository, None]:
    """Dependency injector for PostgresDatasetRepository."""
    async with get_session() as session:
        yield PostgresDatasetRepository(session=session)


async def get_enrichment_repository() -> AsyncGenerator[PostgresEnrichmentRepository, None]:
    """Dependency injector for PostgresEnrichmentRepository."""
    async with get_session() as session:
        yield PostgresEnrichmentRepository(session=session)


async def get_file_repository() -> AsyncGenerator[PostgresFileRepository, None]:
    """Dependency injector for PostgresFileRepository."""
    async with get_session() as session:
        yield PostgresFileRepository(session=session)


async def get_enrichment_run_repository() -> AsyncGenerator[PostgresEnrichmentRunRepository, None]:
    """Dependency injector for PostgresEnrichmentRunRepository."""
    async with get_session() as session:
        yield PostgresEnrichmentRunRepository(session=session)


async def get_extracted_text_repository() -> AsyncGenerator[PostgresExtractedTextRepository, None]:
    """Dependency injector for PostgresExtractedTextRepository."""
    async with get_session() as session:
        yield PostgresExtractedTextRepository(session=session)


async def get_image_repository() -> AsyncGenerator[PostgresImageRepository, None]:
    """Dependency injector for PostgresImageRepository."""
    async with get_session() as session:
        yield PostgresImageRepository(session=session)


async def get_database_metrics_repository() -> AsyncGenerator[PostgresDatabaseMetricsRepository, None]:
    """Dependency injector for PostgresDatabaseMetricsRepository."""
    async with get_session() as session:
        yield PostgresDatabaseMetricsRepository(session=session)


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


async def get_entity_repository() -> AsyncGenerator[PostgresEntityRepository, None]:
    """Dependency injector for PostgresEntityRepository."""
    async with get_session() as session:
        yield PostgresEntityRepository(session=session)


async def get_mention_repository() -> AsyncGenerator[PostgresMentionRepository, None]:
    """Dependency injector for PostgresMentionRepository."""
    async with get_session() as session:
        yield PostgresMentionRepository(session=session)


async def get_location_repository() -> AsyncGenerator[PostgresLocationRepository, None]:
    """Dependency injector for PostgresLocationRepository."""
    async with get_session() as session:
        yield PostgresLocationRepository(session=session)


async def get_graph_repository() -> AsyncGenerator[PostgresGraphRepository, None]:
    """Dependency injector for PostgresGraphRepository."""
    async with get_session() as session:
        yield PostgresGraphRepository(session=session)


async def get_relationship_candidate_repository() -> AsyncGenerator[PostgresRelationshipCandidateRepository, None]:
    """Dependency injector for PostgresRelationshipCandidateRepository."""
    async with get_session() as session:
        yield PostgresRelationshipCandidateRepository(session=session)


async def get_entity_match_repository() -> AsyncGenerator[PostgresEntityMatchRepository, None]:
    """Dependency injector for PostgresEntityMatchRepository."""
    async with get_session() as session:
        yield PostgresEntityMatchRepository(session=session)


async def get_event_repository() -> AsyncGenerator[PostgresEventRepository, None]:
    """Dependency injector for PostgresEventRepository."""
    async with get_session() as session:
        yield PostgresEventRepository(session=session)


async def get_tag_repository() -> AsyncGenerator[PostgresTagRepository, None]:
    """Dependency injector for PostgresTagRepository."""
    async with get_session() as session:
        yield PostgresTagRepository(session=session)


DatasetDatastoreDep = Annotated[PostgresDatasetRepository, Depends(get_dataset_repository)]
EnrichmentDatastoreDep = Annotated[PostgresEnrichmentRepository, Depends(get_enrichment_repository)]
EnrichmentRunDatastoreDep = Annotated[PostgresEnrichmentRunRepository, Depends(get_enrichment_run_repository)]
FileDatastoreDep = Annotated[PostgresFileRepository, Depends(get_file_repository)]
ExtractedTextDatastoreDep = Annotated[PostgresExtractedTextRepository, Depends(get_extracted_text_repository)]
ImageDatastoreDep = Annotated[PostgresImageRepository, Depends(get_image_repository)]
UserDatastoreDep = Annotated[PostgresUserRepository, Depends(get_user_repository)]
DatabaseMetricsDatastoreDep = Annotated[PostgresDatabaseMetricsRepository, Depends(get_database_metrics_repository)]
FaceDatastoreDep = Annotated[PostgresFaceRepository, Depends(get_face_repository)]
PersonDatastoreDep = Annotated[PostgresPersonRepository, Depends(get_person_repository)]
CommentDatastoreDep = Annotated[PostgresCommentRepository, Depends(get_comment_repository)]
FaceMatchDatastoreDep = Annotated[PostgresFaceMatchRepository, Depends(get_face_match_repository)]
EntityDatastoreDep = Annotated[PostgresEntityRepository, Depends(get_entity_repository)]
MentionDatastoreDep = Annotated[PostgresMentionRepository, Depends(get_mention_repository)]
LocationDatastoreDep = Annotated[PostgresLocationRepository, Depends(get_location_repository)]
GraphDatastoreDep = Annotated[PostgresGraphRepository, Depends(get_graph_repository)]
RelationshipCandidateDatastoreDep = Annotated[
    PostgresRelationshipCandidateRepository, Depends(get_relationship_candidate_repository)
]
EntityMatchDatastoreDep = Annotated[PostgresEntityMatchRepository, Depends(get_entity_match_repository)]
EventDatastoreDep = Annotated[PostgresEventRepository, Depends(get_event_repository)]
TagDatastoreDep = Annotated[PostgresTagRepository, Depends(get_tag_repository)]


def image_similarity_params_form(
    page: Annotated[int, Form(ge=1)],
    limit: Annotated[int, Form(ge=1, le=100)] = 10,
    sort_by: Annotated[str, Form(alias="sortBy")] = ImageSortField.SIMILARITY,
    sort_order: Annotated[SortOrder, Form(alias="sortOrder")] = SortOrder.DESC,
    min_similarity: Annotated[float | None, Form(alias="minSimilarity", ge=0.0, le=1.0)] = None,
    date_from: Annotated[str | None, Form(alias="dateFrom")] = None,
    date_to: Annotated[str | None, Form(alias="dateTo")] = None,
    datasets: Annotated[list[str] | None, Form()] = None,
    filetypes: Annotated[list[str] | None, Form()] = None,
    tags: Annotated[list[str] | None, Form()] = None,
    negative_tags: Annotated[list[str] | None, Form(alias="negativeTags")] = None,
    predicted_tags: Annotated[list[str] | None, Form(alias="predictedTags")] = None,
    min_tag_score: Annotated[float, Form(alias="minTagScore", ge=0.0, le=1.0)] = 0.5,
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
            "negative_tags": negative_tags,
            "predicted_tags": predicted_tags,
            "min_tag_score": min_tag_score,
        }
    )


ImageSimilaritySearchFormParametersDep = Annotated[
    ImageSimilaritySearchParameters, Depends(image_similarity_params_form)
]


def face_similarity_params_form(
    page: Annotated[int, Form(ge=1)],
    limit: Annotated[int, Form(ge=1, le=100)] = 10,
    sort_by: Annotated[str, Form(alias="sortBy")] = FaceSortField.SIMILARITY,
    sort_order: Annotated[SortOrder, Form(alias="sortOrder")] = SortOrder.DESC,
    min_similarity: Annotated[float | None, Form(alias="minSimilarity", ge=0.0, le=1.0)] = None,
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


FaceSimilaritySearchFormParametersDep = Annotated[FaceSimilaritySearchParameters, Depends(face_similarity_params_form)]


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
    "get_enrichment_run_repository",
    "get_file_repository",
    "get_extracted_text_repository",
    "get_image_repository",
    "get_face_repository",
    "get_person_repository",
    "get_comment_repository",
    "get_face_match_repository",
    "get_entity_repository",
    "get_mention_repository",
    "get_location_repository",
    "get_graph_repository",
    "get_relationship_candidate_repository",
    "get_entity_match_repository",
    "get_event_repository",
    "DatasetDatastoreDep",
    "EnrichmentDatastoreDep",
    "EnrichmentRunDatastoreDep",
    "FileDatastoreDep",
    "ExtractedTextDatastoreDep",
    "ImageDatastoreDep",
    "ImageSimilaritySearchFormParametersDep",
    "FaceDatastoreDep",
    "PersonDatastoreDep",
    "CommentDatastoreDep",
    "FaceMatchDatastoreDep",
    "EntityDatastoreDep",
    "MentionDatastoreDep",
    "LocationDatastoreDep",
    "GraphDatastoreDep",
    "RelationshipCandidateDatastoreDep",
    "EntityMatchDatastoreDep",
    "EventDatastoreDep",
    "TagDatastoreDep",
    "FaceSimilaritySearchFormParametersDep",
    "postgres_lifespan",
]
