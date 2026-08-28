"""Alembic environment.

Resolves the database URL from `ALEMBIC_DATABASE_URL`, or from the same
`POSTGRES__*` variables (in `.env`) the services use. `target_metadata` is the
shared `Base.metadata`; importing the tables package registers every model.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import cipher.datastores.postgres.tables  # noqa: F401  (registers every table on Base.metadata)
from cipher.datastores.postgres.tables.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    explicit = os.environ.get("ALEMBIC_DATABASE_URL")
    if explicit:
        return explicit

    try:
        from pydantic_settings import BaseSettings, SettingsConfigDict

        from cipher.datastores.postgres.config import PostgresConfig

        class _Env(BaseSettings):
            model_config = SettingsConfigDict(
                env_file=".env", env_nested_delimiter="__", extra="ignore"
            )
            postgres: PostgresConfig

        pg = _Env().postgres  # type: ignore[call-arg]
        return (
            f"postgresql+psycopg2://{pg.username}:{pg.password}"
            f"@{pg.host}:{pg.port}/{pg.database}"
        )
    except Exception as exc:  # pragma: no cover - configuration error path
        raise RuntimeError(
            "Set ALEMBIC_DATABASE_URL or POSTGRES__HOST/PORT/USERNAME/PASSWORD/DATABASE"
        ) from exc


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
