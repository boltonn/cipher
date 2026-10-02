"""Positive / negative tags on `file`, plus model confidence per tag.

`file.tags` / `file.negative_tags` are labels for training classifiers over a
file's embeddings ("is this" / "is explicitly not this"). `file.tag_scores` is
a model's confidence that a tag applies (`{tag: 0-1}`) -- a prediction, kept
apart from the labels so the two can be compared.

Revision ID: 0032_file_tags
Revises: 0031_event_type_gathering
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0032_file_tags"
down_revision: str | None = "0031_event_type_gathering"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TAG_COLUMNS = ("tags", "negative_tags")


def upgrade() -> None:
    for column in _TAG_COLUMNS:
        op.add_column("file", sa.Column(column, JSONB, nullable=False, server_default="[]"))
        op.create_index(f"ix_file_{column}_gin", "file", [column], postgresql_using="gin")
    op.add_column("file", sa.Column("tag_scores", JSONB, nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("file", "tag_scores")
    for column in _TAG_COLUMNS:
        op.drop_index(f"ix_file_{column}_gin", table_name="file")
        op.drop_column("file", column)
