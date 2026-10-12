"""`file`: unique per place found (`dataset_id, path`), plus `compression`.

Content-addressed blobs (archive members, decompressed files) let many rows share one `uri`,
so a row is identified by where the file was found (`path`) instead. `compression` records
the encoding a file was found in with the as-found bytes' hashes (`CompressionInfo`).

Revision ID: 0050_file_found_at_compression
Revises: 0049_enrichment_run_progress
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0050_file_found_at_compression"
down_revision: str | None = "0049_enrichment_run_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Swap the unique key to `(dataset_id, path)` and add `compression`."""
    op.create_unique_constraint("uq_dataset_path", "file", ["dataset_id", "path"])
    op.drop_constraint("uq_dataset_uri", "file", type_="unique")
    op.add_column("file", sa.Column("compression", JSONB(), nullable=True))


def downgrade() -> None:
    """Back to `(dataset_id, uri)` (fails if rows now share a uri) and drop `compression`."""
    op.drop_column("file", "compression")
    op.create_unique_constraint("uq_dataset_uri", "file", ["dataset_id", "uri"])
    op.drop_constraint("uq_dataset_path", "file", type_="unique")
