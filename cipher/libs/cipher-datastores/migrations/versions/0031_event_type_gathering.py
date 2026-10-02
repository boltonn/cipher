"""Drop the `deadline` event type and rename `occasion` to `gathering`.

A deadline is not an occurrence anyone attends, so existing rows fall back to
`OTHER` (their `details` blob no longer validates and is cleared). `occasion`
was an undefined catch-all; `gathering` names what it was for. The column is a
non-native Enum storing the member name.

Revision ID: 0031_event_type_gathering
Revises: 0030_location_source_rename
Create Date: 2026-10-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031_event_type_gathering"
down_revision: str | None = "0030_location_source_rename"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE event SET event_type = 'GATHERING' WHERE event_type = 'OCCASION'")
    op.execute("UPDATE event SET event_type = 'OTHER', details = NULL WHERE event_type = 'DEADLINE'")


def downgrade() -> None:
    op.execute("UPDATE event SET event_type = 'OCCASION' WHERE event_type = 'GATHERING'")
