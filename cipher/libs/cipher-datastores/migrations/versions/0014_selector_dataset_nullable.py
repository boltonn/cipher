"""Make `selector.dataset_id` nullable for analyst-attached selectors.

A selector known from external knowledge (an analyst linking a phone/handle to a
person) is not an artefact of one ingest -- like a person bridge node it carries
no dataset. `selector.dataset_id` becomes nullable, and the single blocking-key
constraint splits into two partial unique indexes:

- `uq_selector_dataset_type_value` -- `(dataset_id, selector_type,
  normalized_value)` where `dataset_id IS NOT NULL` (extracted selectors)
- `uq_selector_global_type_value` -- `(selector_type, normalized_value)` where
  `dataset_id IS NULL` (globally unique analyst-attached selectors)

Revision ID: 0014_selector_dataset_nullable
Revises: 0013_location_text_mentions
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_selector_dataset_nullable"
down_revision: str | None = "0013_location_text_mentions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_selector_dataset_type_value", "selector", type_="unique")
    op.alter_column("selector", "dataset_id", existing_type=sa.String(), nullable=True)
    op.execute(
        "CREATE UNIQUE INDEX uq_selector_dataset_type_value ON selector "
        "(dataset_id, selector_type, normalized_value) WHERE dataset_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_selector_global_type_value ON selector "
        "(selector_type, normalized_value) WHERE dataset_id IS NULL"
    )


def downgrade() -> None:
    op.execute("DELETE FROM selector WHERE dataset_id IS NULL")
    op.drop_index("uq_selector_global_type_value", table_name="selector")
    op.drop_index("uq_selector_dataset_type_value", table_name="selector")
    op.alter_column("selector", "dataset_id", existing_type=sa.String(), nullable=False)
    op.create_unique_constraint(
        "uq_selector_dataset_type_value", "selector", ["dataset_id", "selector_type", "normalized_value"]
    )
