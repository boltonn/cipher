"""Add `dataset.date_staged` -- the staging milestone.

Set the first time files are loaded + typed for a dataset (and left set
thereafter). It marks the point the file inventory is fixed, which is what
enrichment time estimates key off. Purely additive; nullable, no backfill
(existing datasets read as "staged" from having files, `date_staged` stays
null until the next load).

Revision ID: 0021_dataset_staging
Revises: 0020_entity_match_decision_source
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_dataset_staging"
down_revision: str | None = "0020_entity_match_decision_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("dataset", sa.Column("date_staged", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("dataset", "date_staged")
