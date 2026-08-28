"""Baseline: all pre-entity-layer tables plus required extensions.

Captures the schema as it stood before the entity/ontology layer. Existing
databases created via `Base.metadata.create_all` can adopt migrations with
`alembic stamp 0001_baseline` instead of running this.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op

from cipher.datastores.postgres.tables.base import Base
from migrations._tables import ENTITY_LAYER_TABLE_NAMES

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _baseline_tables():
    return [t for t in Base.metadata.sorted_tables if t.name not in ENTITY_LAYER_TABLE_NAMES]


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    Base.metadata.create_all(bind=bind, tables=_baseline_tables(), checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=list(reversed(_baseline_tables())), checkfirst=True)
