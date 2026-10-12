"""Index `extracted_text.metadata->>'conversation_id'`: an email's conversation.

The email viewer lists the other emails sharing `EmailMetadata.conversation_id`.

Revision ID: 0053_email_conversation_id_index
Revises: 0052_email_meaningful_hash_index
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0053_email_conversation_id_index"
down_revision: str | None = "0052_email_meaningful_hash_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Partial expression index over emails that have a conversation id."""
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_extracted_text_conversation_id ON extracted_text "
        "((metadata->>'conversation_id')) WHERE metadata ? 'conversation_id'"
    )


def downgrade() -> None:
    """Drop the index."""
    op.execute("DROP INDEX IF EXISTS ix_extracted_text_conversation_id")
