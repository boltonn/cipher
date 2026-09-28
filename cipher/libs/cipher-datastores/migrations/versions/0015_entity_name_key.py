"""Add the entity_name_key table.

A materialized blocking index for entity resolution: the transliterated /
phonetic / sorted-token / surname / given+surname forms of every person /
organization / location entity's display name and aliases, computed by
`cipher.names.entity_keys`. An unresolved mention's keys equality-join this
table to generate candidate entities.

Purely additive -- no existing table is altered. Populate with
`cipher backfill-entity-name-keys`; thereafter it is kept current by an inline
refresh on every entity write and `ON DELETE CASCADE` from `entity`.

Revision ID: 0015_entity_name_key
Revises: 0014_selector_dataset_nullable
Create Date: 2026-09-06
"""

from collections.abc import Sequence

from alembic import op

from cipher.datastores.postgres.tables.base import Base
from cipher.datastores.postgres.tables.entity_name_key import EntityNameKeyTable

revision: str = "0015_entity_name_key"
down_revision: str | None = "0014_selector_dataset_nullable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[EntityNameKeyTable.__table__], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[EntityNameKeyTable.__table__], checkfirst=True)
