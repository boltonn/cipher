"""`file.is_encrypted`: encrypted as found (an archive with encrypted members, a password-protected file).

Set by filetyper (zip member flags, PDF `/Encrypt`, encrypted Office packages) and by archive
extraction (7z / rar listings). `cipher rekey --filetypes` fills it for files already loaded.

Revision ID: 0051_file_is_encrypted
Revises: 0050_file_found_at_compression
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051_file_is_encrypted"
down_revision: str | None = "0050_file_found_at_compression"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the flag (false for every existing row)."""
    op.add_column("file", sa.Column("is_encrypted", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Drop the flag."""
    op.drop_column("file", "is_encrypted")
