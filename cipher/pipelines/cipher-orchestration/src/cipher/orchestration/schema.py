"""Database schema setup."""

from typing import TYPE_CHECKING

from sqlalchemy import text

# Importing the tables package registers every table class on the shared
# Base.metadata, in FK-dependency order, as a side effect.
import cipher.datastores.postgres.tables as tables  # noqa: F401
from cipher.datastores.postgres.tables.base import Base

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def create_tables(session: "AsyncSession") -> None:
    """Create every registered table (idempotent) and enable pgvector + pg_trgm."""
    async with session.bind.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)
