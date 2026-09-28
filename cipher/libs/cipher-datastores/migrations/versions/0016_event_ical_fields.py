"""Event layer: carry the iCalendar (RFC 5545 VEVENT) fields losslessly.

The `.ics` parser (`pyparse.parsers.calendar.ics`) already reads these, but the
mapping onto `event` dropped them. Purely additive -- every column is nullable or
defaulted, so this is a safe no-op on a `create_all` database.

- **event**: `url`, `categories` (raw source labels, distinct from analyst
  `tags`), `sensitivity` (iCalendar `CLASS`), `uid` (identity key across
  updates), `recurrence_rule` (raw `RRULE`, not expanded), `sequence`
  (source revision), `source_created` / `source_last_modified`.
- **event_participant**: `raw_email` (calendar address -- the precise key for
  resolution), `rsvp_status` (iCalendar `PARTSTAT`), `is_resource` (a room /
  resource, not a person).

Revision ID: 0016_event_ical_fields
Revises: 0015_entity_name_key
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_event_ical_fields"
down_revision: str | None = "0015_entity_name_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("event", sa.Column("url", sa.String(), nullable=True))
    op.add_column(
        "event",
        sa.Column("categories", postgresql.JSONB(), server_default="[]", nullable=False),
    )
    op.add_column("event", sa.Column("sensitivity", sa.String(length=32), nullable=True))
    op.add_column("event", sa.Column("uid", sa.String(), nullable=True))
    op.add_column("event", sa.Column("recurrence_rule", sa.String(), nullable=True))
    op.add_column("event", sa.Column("sequence", sa.Integer(), nullable=True))
    op.add_column("event", sa.Column("source_created", sa.DateTime(timezone=True), nullable=True))
    op.add_column("event", sa.Column("source_last_modified", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_event_uid", "event", ["uid"])

    op.add_column("event_participant", sa.Column("raw_email", sa.String(), nullable=True))
    op.add_column("event_participant", sa.Column("rsvp_status", sa.String(length=32), nullable=True))
    op.add_column(
        "event_participant",
        sa.Column("is_resource", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index("ix_event_participant_raw_email", "event_participant", ["raw_email"])


def downgrade() -> None:
    op.drop_index("ix_event_participant_raw_email", table_name="event_participant")
    op.drop_column("event_participant", "is_resource")
    op.drop_column("event_participant", "rsvp_status")
    op.drop_column("event_participant", "raw_email")

    op.drop_index("ix_event_uid", table_name="event")
    op.drop_column("event", "source_last_modified")
    op.drop_column("event", "source_created")
    op.drop_column("event", "sequence")
    op.drop_column("event", "recurrence_rule")
    op.drop_column("event", "uid")
    op.drop_column("event", "sensitivity")
    op.drop_column("event", "categories")
    op.drop_column("event", "url")
