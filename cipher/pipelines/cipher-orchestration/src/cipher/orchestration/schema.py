"""Database schema setup."""

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text

# Importing the tables package registers every table class on the shared
# Base.metadata, in FK-dependency order, as a side effect.
import cipher.datastores.postgres.tables as tables  # noqa: F401
from cipher.datastores.postgres.tables.base import Base

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

EXTENSIONS = ["vector", "pg_trgm", "postgis", "unaccent", "pg_search"]
# Objects the table models don't declare (migrations add them on upgraded databases).
EXTRAS = [
    """CREATE INDEX IF NOT EXISTS ix_chunk_text_bm25 ON chunk
       USING bm25 (id, text, dataset_id, filetype_group, file_id, language)
       WITH (key_field=id, text_fields='{"text": {"tokenizer": {"type": "icu"}}}')""",
    "ALTER TABLE chunk ALTER COLUMN date_created SET DEFAULT now()",
    "ALTER TABLE event ALTER COLUMN categories SET DEFAULT '[]'::jsonb",
    "ALTER TABLE event_participant ALTER COLUMN is_resource SET DEFAULT false",
    "ALTER TABLE location ALTER COLUMN tags SET DEFAULT '[]'::jsonb",
]
ALEMBIC_DIR = Path(__file__).resolve().parents[5] / "libs" / "cipher-datastores"


async def create_tables(session: "AsyncSession") -> None:
    """Create every registered table plus the extensions and extras the models need (idempotent)."""
    async with session.bind.begin() as conn:
        for extension in EXTENSIONS:
            await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {extension}"))
        await conn.run_sync(Base.metadata.create_all)
        for statement in EXTRAS:
            await conn.execute(text(statement))


def stamp_head() -> None:
    """Mark the database as at the latest migration -- only for one `create_tables` just built from empty.

    `alembic upgrade head` can't build an empty database (the baseline creates tables from the
    live models, then early revisions re-add existing columns), so new databases are built with
    `create_tables` and stamped; later revisions then apply with `alembic upgrade head`.
    """
    from alembic import command
    from alembic.config import Config

    sys.path.insert(0, str(ALEMBIC_DIR))  # revisions import `migrations._tables`
    config = Config(str(ALEMBIC_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(ALEMBIC_DIR / "migrations"))
    command.stamp(config, "head")
