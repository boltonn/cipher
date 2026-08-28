"""Allow entity.dataset_id to be NULL (person bridge nodes span datasets).

Revision ID: 0004_entity_dataset_nullable
Revises: 0003_mention_entity_attribute
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_entity_dataset_nullable"
down_revision: str | None = "0003_mention_entity_attribute"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("entity", "dataset_id", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM entity WHERE dataset_id IS NULL")
    op.alter_column("entity", "dataset_id", existing_type=sa.String(), nullable=False)
