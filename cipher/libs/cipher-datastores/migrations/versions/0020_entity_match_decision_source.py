"""Add entity_match.decision_source.

Records how a match's status was set -- `analyst` (explicit queue decision),
`sibling_auto` (rejected because a sibling was confirmed), `reconcile` (closed by
the sweep), `system_auto` (the one always-auto rule) -- so weight calibration can
tell a real analyst label from a derived one. Nullable; purely additive.

Revision ID: 0020_entity_match_decision_source
Revises: 0019_chunk_table
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_entity_match_decision_source"
down_revision: str | None = "0019_chunk_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("entity_match", sa.Column("decision_source", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("entity_match", "decision_source")
