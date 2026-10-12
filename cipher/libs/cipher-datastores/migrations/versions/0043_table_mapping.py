"""`table_mapping` + `file.table_sheets`: column mappings for tabular files.

A mapping is shared by every file in a dataset with the same header layout
(`fingerprint`), so one review covers a whole export. `file.table_sheets` records
where each of a file's sheets keeps its header and data, and which layout it has.
See docs/tabular-mapping.md.

Revision ID: 0043_table_mapping
Revises: 0042_global_search
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0043_table_mapping"
down_revision: str | None = "0042_global_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the table and the file column."""
    op.create_table(
        "table_mapping",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dataset_id", sa.String(), sa.ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("mapping", JSONB, nullable=False),
        sa.Column("sample", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verified_by", sa.String(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("date_verified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_created", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("date_updated", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("dataset_id", "fingerprint", name="uq_table_mapping_dataset_fingerprint"),
        if_not_exists=True,
    )
    op.add_column("file", sa.Column("table_sheets", JSONB, nullable=True))
    op.create_index(
        "ix_file_table_sheets_gin",
        "file",
        ["table_sheets"],
        postgresql_using="gin",
        postgresql_ops={"table_sheets": "jsonb_path_ops"},
    )


def downgrade() -> None:
    """Drop the column and the table."""
    op.drop_column("file", "table_sheets")
    op.drop_table("table_mapping")
