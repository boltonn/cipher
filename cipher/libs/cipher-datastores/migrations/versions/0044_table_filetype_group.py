"""Spreadsheets get their own filetype group: `table` (csv, tsv, xlsx, xls, xlsb, ods, parquet).

Like `image`, a table has its own page (`/tables/{sha256}`) and pipeline (table mappings),
so files staged before filetyper's registry changed are moved over. json/jsonl stay
`document`: most JSON files are not tables (`cipher map-tables` still reads them).

Revision ID: 0044_table_filetype_group
Revises: 0043_table_mapping
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044_table_filetype_group"
down_revision: str | None = "0043_table_mapping"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GROUPS = {
    "csv": "document",
    "tsv": "document",
    "xlsx": "document",
    "xls": "document",
    "xlsb": "document",
    "ods": "document",
    "parquet": "unknown",
}


def upgrade() -> None:
    """Regroup existing spreadsheet files."""
    op.get_bind().execute(
        sa.text("UPDATE file SET filetype_group = 'table' WHERE filetype = ANY(:filetypes)"),
        {"filetypes": list(_GROUPS)},
    )


def downgrade() -> None:
    """Back to the groups they had before."""
    for filetype, group in _GROUPS.items():
        op.get_bind().execute(
            sa.text("UPDATE file SET filetype_group = :group WHERE filetype = :filetype AND filetype_group = 'table'"),
            {"group": group, "filetype": filetype},
        )
