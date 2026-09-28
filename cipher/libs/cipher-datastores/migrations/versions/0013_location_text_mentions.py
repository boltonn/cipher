"""Let a file carry many `location` points from free-text coordinates.

`uq_location_file_source` (one point per file per source, for single-fix sources
like EXIF) becomes a partial unique index that excludes ``source =
'TEXT_MENTION'`` (the non-native Enum column stores the member name) -- a
document can name several coordinates, each its own row.

Revision ID: 0013_location_text_mentions
Revises: 0012_selector_attributes
Create Date: 2026-09-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_location_text_mentions"
down_revision: str | None = "0012_selector_attributes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_location_file_source", "location", type_="unique")
    op.execute(
        "CREATE UNIQUE INDEX uq_location_file_source ON location (file_id, source) "
        "WHERE source <> 'TEXT_MENTION'"
    )


def downgrade() -> None:
    op.execute("DELETE FROM location WHERE source = 'TEXT_MENTION'")
    op.drop_index("uq_location_file_source", table_name="location")
    op.create_unique_constraint("uq_location_file_source", "location", ["file_id", "source"])
