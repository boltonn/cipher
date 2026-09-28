"""Add entity_match.explanation (the per-feature resolution 'why').

The Fellegi-Sunter scorer stores a `ResolutionExplanation` (score, band,
per-feature match weights + reasons) on every candidate it emits, so the review
queue can render a waterfall and an analyst can see exactly why a mention
resolved -- or didn't. Purely additive.

Revision ID: 0017_entity_match_explanation
Revises: 0016_event_ical_fields
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_entity_match_explanation"
down_revision: str | None = "0016_event_ical_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("entity_match", sa.Column("explanation", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("entity_match", "explanation")
