"""`file.source_tags` + `file.message_states`: what the data itself says, filterable.

Gmail's inbox categories and a message's states (spam, sent, ...) are parsed into
`extracted_text.metadata`; these GIN-indexed copies let chunk search filter on them.
Backfilled through the same schema logic the extraction upsert uses.

Revision ID: 0040_file_source_tags
Revises: 0039_candidate_explanation
Create Date: 2026-10-03
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from cipher.schemas.content.email import EmailMetadata

revision: str = "0040_file_source_tags"
down_revision: str | None = "0039_candidate_explanation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("source_tags", "message_states")


def upgrade() -> None:
    """Add the columns + indexes, then backfill from email metadata."""
    for column in _COLUMNS:
        op.add_column("file", sa.Column(column, JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
        op.create_index(f"ix_file_{column}_gin", "file", [column], postgresql_using="gin")

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT file_id, metadata FROM extracted_text WHERE metadata ? 'email_client'"))
    updates = []
    for file_id, metadata in rows:
        email = EmailMetadata.model_validate(metadata)
        source_tags = [category.value for category in email.client_categories()]
        message_states = [state.value for state in email.message_states()]
        if source_tags or message_states:
            updates.append(
                {"id": file_id, "source_tags": json.dumps(source_tags), "message_states": json.dumps(message_states)}
            )
    if updates:
        bind.execute(
            sa.text(
                "UPDATE file SET source_tags = cast(:source_tags AS jsonb), "
                "message_states = cast(:message_states AS jsonb) WHERE id = :id"
            ),
            updates,
        )


def downgrade() -> None:
    """Drop the columns (their indexes go with them)."""
    for column in _COLUMNS:
        op.drop_column("file", column)
