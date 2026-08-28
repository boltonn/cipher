"""Add mention.entity_attribute (evidence points at a named entity attribute).

Revision ID: 0003_mention_entity_attribute
Revises: 0002_entities
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_mention_entity_attribute"
down_revision: str | None = "0002_entities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mention", sa.Column("entity_attribute", sa.String(), nullable=True))
    op.create_index(
        "ix_mention_entity_attribute", "mention", ["entity_id", "entity_attribute"]
    )


def downgrade() -> None:
    op.drop_index("ix_mention_entity_attribute", table_name="mention")
    op.drop_column("mention", "entity_attribute")
