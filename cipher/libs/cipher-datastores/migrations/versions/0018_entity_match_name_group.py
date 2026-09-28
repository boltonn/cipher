"""entity_match: carry a name-group key so one candidate resolves a whole name.

`resolve-entities` scores a candidate per *name group* (all unresolved `name`
mentions of one `normalized_value`), not per mention -- a common name is one
decision, not thousands. A group-level `entity_match` has `mention_id IS NULL`
and instead carries `normalized_value` + `mention_count`; confirming it
bulk-attaches every unresolved mention of that value.

Revision ID: 0018_entity_match_name_group
Revises: 0017_entity_match_explanation
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_entity_match_name_group"
down_revision: str | None = "0017_entity_match_explanation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("entity_match", sa.Column("normalized_value", sa.String(), nullable=True))
    op.add_column("entity_match", sa.Column("mention_count", sa.Integer(), nullable=True))
    op.execute(
        "CREATE UNIQUE INDEX uq_entity_match_name_group ON entity_match "
        "(dataset_id, normalized_value, entity_id) "
        "WHERE mention_id IS NULL AND normalized_value IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("uq_entity_match_name_group", table_name="entity_match")
    op.drop_column("entity_match", "mention_count")
    op.drop_column("entity_match", "normalized_value")
