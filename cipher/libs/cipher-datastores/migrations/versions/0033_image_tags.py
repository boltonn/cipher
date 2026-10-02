"""Negative tags on `image`, plus model confidence per tag.

Mirrors `0032_file_tags`: `image.tags` (already present) / `image.negative_tags`
are labels for training classifiers over an image's embedding ("is this" / "is
explicitly not this"). `image.tag_scores` is a model's confidence that a tag
applies (`{tag: 0-1}`) -- a prediction, kept apart from the labels so an analyst
can accept or reject it.

Revision ID: 0033_image_tags
Revises: 0032_file_tags
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0033_image_tags"
down_revision: str | None = "0032_file_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("image", sa.Column("negative_tags", JSONB, nullable=False, server_default="[]"))
    op.create_index("ix_image_negative_tags_gin", "image", ["negative_tags"], postgresql_using="gin")
    op.add_column("image", sa.Column("tag_scores", JSONB, nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("image", "tag_scores")
    op.drop_index("ix_image_negative_tags_gin", table_name="image")
    op.drop_column("image", "negative_tags")
