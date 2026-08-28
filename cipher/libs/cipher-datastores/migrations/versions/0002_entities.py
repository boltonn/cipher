"""Entity / ontology / knowledge-graph layer tables.

Adds: entity, organization, location, selector, mention, entity_relationship,
entity_relationship_candidate, entity_match (with their trigram GIN, HNSW, and
partial indexes). Purely additive -- no existing table is altered.

Revision ID: 0002_entities
Revises: 0001_baseline
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op

from cipher.datastores.postgres.tables.base import Base
from migrations._tables import entity_layer_tables

revision: str = "0002_entities"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    Base.metadata.create_all(bind=bind, tables=entity_layer_tables(), checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=list(reversed(entity_layer_tables())), checkfirst=True)
