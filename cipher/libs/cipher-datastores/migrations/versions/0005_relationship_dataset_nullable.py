"""Allow entity_relationship.dataset_id to be NULL.

An edge between two dataset-agnostic nodes (e.g. family_of between two person
bridge nodes) belongs to no single dataset. Mirrors 0004 for entity.dataset_id.

Revision ID: 0005_relationship_dataset_nullable
Revises: 0004_entity_dataset_nullable
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_relationship_dataset_nullable"
down_revision: str | None = "0004_entity_dataset_nullable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("entity_relationship", "dataset_id", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM entity_relationship WHERE dataset_id IS NULL")
    op.alter_column("entity_relationship", "dataset_id", existing_type=sa.String(), nullable=False)
