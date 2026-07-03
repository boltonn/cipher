import asyncio
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from cipher.datastores.postgres.config import PostgresConfig
from cipher.datastores.postgres.tables.base import Base


@lru_cache(maxsize=1)
def get_async_engine(config: PostgresConfig) -> AsyncEngine:
    """Return a cached AsyncEngine; called once per process."""
    database_url = (
        f"postgresql+asyncpg://{config.username}:{config.password}"
        f"@{config.host}:{config.port}/{config.database}"
    )
    engine = create_async_engine(
        database_url,
        pool_size=config.pool_size,
        max_overflow=config.max_overflow,
    )
    return engine


async def init_db(config: PostgresConfig):
    """Initialize the database by creating all tables."""
    async with get_async_engine(config).begin() as conn:
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
