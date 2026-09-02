"""Event layer: event, event_participant, event_place.

Dated occurrences (travel, lodging, reservations, meetings, deadlines,
deliveries) extracted from documents or parsed from calendar attachments, plus
their links to people (-> entity) and places (-> location). Purely additive --
no existing table is altered.

Revision ID: 0008_events
Revises: 0007_widen_enrichment_type
Create Date: 2026-09-02
"""

from collections.abc import Sequence

from alembic import op
from migrations._tables import event_layer_tables

from cipher.datastores.postgres.tables.base import Base

revision: str = "0008_events"
down_revision: str | None = "0007_widen_enrichment_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=event_layer_tables(), checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=list(reversed(event_layer_tables())), checkfirst=True)
