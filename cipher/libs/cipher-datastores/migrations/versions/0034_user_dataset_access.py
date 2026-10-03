"""Dataset access control: admins, membership grant dates, discoverable datasets.

A `user_dataset_access` row makes a user a member of a dataset; `user.is_admin`
sees every dataset without one. Membership is meant to be synced from an
external entitlement source, so there are no per-dataset roles here.
`dataset.is_discoverable` lists a dataset (locked) to users who aren't members.

Revision ID: 0034_user_dataset_access
Revises: 0033_image_tags
Create Date: 2026-10-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0034_user_dataset_access"
down_revision: str | None = "0033_image_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # IF NOT EXISTS: `0001_baseline` builds tables from the live metadata, so a fresh database has these already.
    op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_admin boolean NOT NULL DEFAULT false')
    op.execute(
        "ALTER TABLE user_dataset_access ADD COLUMN IF NOT EXISTS date_granted timestamptz NOT NULL DEFAULT now()"
    )
    op.execute("ALTER TABLE dataset ADD COLUMN IF NOT EXISTS is_discoverable boolean NOT NULL DEFAULT false")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_dataset_access_dataset_id ON user_dataset_access (dataset_id)")
    op.execute("UPDATE \"user\" SET is_admin = true WHERE email = 'dev-admin@cipher.local'")


def downgrade() -> None:
    op.drop_index("ix_user_dataset_access_dataset_id", table_name="user_dataset_access")
    op.drop_column("user_dataset_access", "date_granted")
    op.drop_column("user", "is_admin")
    op.drop_column("dataset", "is_discoverable")
