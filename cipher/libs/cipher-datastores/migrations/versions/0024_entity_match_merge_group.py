"""Add the partial-unique index backing entity->entity merge proposals.

`dedupe-entities` writes `entity_match` rows with `provisional_entity_id` set (and
`mention_id` / `normalized_value` null) -- one per (provisional entity, canonical
candidate). The index keeps a re-run idempotent. Purely additive.

Revision ID: 0024_entity_match_merge_group
Revises: 0023_chunk_search_columns
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_entity_match_merge_group"
down_revision: str | None = "0023_chunk_search_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_entity_match_merge",
        "entity_match",
        ["dataset_id", "provisional_entity_id", "entity_id"],
        unique=True,
        postgresql_where=sa.text("provisional_entity_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_entity_match_merge", table_name="entity_match")
