import asyncio
from functools import lru_cache

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from cipher.datastores.postgres.config import PostgresConfig
from cipher.datastores.postgres.tables.base import Base

# Extensions the app hard-requires (fail loudly if missing) vs. optional ones
# that upgrade multilingual full-text ranking. The keyword-ranker extension
# (`pg_bigm` / `pgroonga` / `pg_search`) is created by the backend from
# `RETRIEVAL__TEXT_RANKER`, not here -- table creation needs none of it.
# See docs/postgres-extensions.md.
_REQUIRED_EXTENSIONS = ("vector", "pg_trgm", "unaccent")
_OPTIONAL_EXTENSIONS: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def get_async_engine(config: PostgresConfig) -> AsyncEngine:
    """Return a cached AsyncEngine; called once per process."""
    database_url = (
        f"postgresql+asyncpg://{config.username}:{config.password}@{config.host}:{config.port}/{config.database}"
    )
    engine = create_async_engine(
        database_url,
        pool_size=config.pool_size,
        max_overflow=config.max_overflow,
        pool_pre_ping=True,
    )
    return engine


async def init_db(config: PostgresConfig):
    """Initialize the database by creating all tables and required extensions.

    Required extensions raise if absent. Optional ones (`pg_bigm`, which needs a
    separately-installed package -- see docs/postgres-extensions.md) are attempted
    and logged; their absence only degrades non-Latin full-text ranking.
    """
    async with get_async_engine(config).begin() as conn:
        for ext in _REQUIRED_EXTENSIONS:
            await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
        for ext in _OPTIONAL_EXTENSIONS:
            try:
                # SAVEPOINT: a missing extension aborts the whole transaction in
                # Postgres ("current transaction is aborted") -- isolate it.
                async with conn.begin_nested():
                    await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
            except Exception as exc:  # noqa: BLE001 -- absence is expected/tolerated
                logger.warning(
                    f"Optional Postgres extension {ext!r} not available "
                    f"({exc.__class__.__name__}); multilingual full-text ranking will "
                    f"fall back to core tsvector. See docs/postgres-extensions.md."
                )
        await conn.run_sync(Base.metadata.create_all)


async def delete_db(config: PostgresConfig):
    """Drop all tables in the database."""
    async with get_async_engine(config).begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def create_tables(config: PostgresConfig):
    """Create all tables in the database."""
    asyncio.run(init_db(config))


def delete_tables(config: PostgresConfig):
    """Drop tables using Base metadata."""
    asyncio.run(delete_db(config))
