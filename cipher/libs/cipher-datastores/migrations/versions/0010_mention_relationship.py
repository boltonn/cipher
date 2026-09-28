"""Add the mention_relationship table.

A relation an extractor asserts between two `mention` spans, recorded before
either span resolves to an entity. `resolve-entities` promotes a row into an
`entity_relationship_candidate` once both endpoints carry an `entity_id`.
Purely additive -- no existing table is altered.

Revision ID: 0010_mention_relationship
Revises: 0009_widen_relationship_type
Create Date: 2026-09-02
"""

from collections.abc import Sequence

from alembic import op

from cipher.datastores.postgres.tables.base import Base
from cipher.datastores.postgres.tables.mention_relationship import MentionRelationshipTable

revision: str = "0010_mention_relationship"
down_revision: str | None = "0009_widen_relationship_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[MentionRelationshipTable.__table__], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[MentionRelationshipTable.__table__], checkfirst=True)
