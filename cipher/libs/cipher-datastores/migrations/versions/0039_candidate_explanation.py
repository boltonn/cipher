"""`entity_relationship_candidate.explanation`: why a suggestion was proposed, for the reviewer.

Revision ID: 0039_candidate_explanation
Revises: 0038_relation_attributes
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0039_candidate_explanation"
down_revision: str | None = "0038_relation_attributes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the column."""
    op.add_column("entity_relationship_candidate", sa.Column("explanation", JSONB, nullable=True))


def downgrade() -> None:
    """Drop the column."""
    op.drop_column("entity_relationship_candidate", "explanation")
