"""`attributes` on `mention_relationship` + `entity_relationship_candidate`.

Lets an extractor's edge detail (a signature's job title -> `role`) ride from the
mention-level relation through review onto the confirmed `entity_relationship`.

Revision ID: 0038_relation_attributes
Revises: 0037_drop_organization_notes
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0038_relation_attributes"
down_revision: str | None = "0037_drop_organization_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("mention_relationship", "entity_relationship_candidate")


def upgrade() -> None:
    """Add the columns."""
    for table in _TABLES:
        op.add_column(table, sa.Column("attributes", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    """Drop the columns."""
    for table in _TABLES:
        op.drop_column(table, "attributes")
