"""Index `extracted_text.metadata->>'meaningful_hash'`: an email's other copies.

Every copy of one message (an inbox and a Sent folder, two mailboxes) has the same
`EmailMetadata.meaningful_hash`; the email view lists the others. Re-extracting emails fills it.

Revision ID: 0052_email_meaningful_hash_index
Revises: 0051_file_is_encrypted
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0052_email_meaningful_hash_index"
down_revision: str | None = "0051_file_is_encrypted"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Partial expression index over emails that have the hash."""
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_extracted_text_meaningful_hash ON extracted_text "
        "((metadata->>'meaningful_hash')) WHERE metadata ? 'meaningful_hash'"
    )


def downgrade() -> None:
    """Drop the index."""
    op.execute("DROP INDEX IF EXISTS ix_extracted_text_meaningful_hash")
