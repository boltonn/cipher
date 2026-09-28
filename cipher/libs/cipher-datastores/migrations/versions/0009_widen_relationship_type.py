"""Widen entity_relationship.relationship_type to fit APPEARS_IN_PHOTO_WITH.

`relationship_type` is `Enum(RelationshipType, native_enum=False)`, which
SQLAlchemy renders as a VARCHAR sized to the longest member *name*. Databases
created before the `appears_in_photo_with` member existed have VARCHAR(17)
(sized to `COMMUNICATES_WITH`), which truncates the 21-char
`APPEARS_IN_PHOTO_WITH` on insert. Fresh `create_all` DBs are already
VARCHAR(21); this brings existing DBs in line.

Revision ID: 0009_widen_relationship_type
Revises: 0008_events
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_widen_relationship_type"
down_revision: str | None = "0008_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "entity_relationship",
        "relationship_type",
        existing_type=sa.String(length=17),
        type_=sa.String(length=21),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.execute("DELETE FROM entity_relationship WHERE char_length(relationship_type) > 17")
    op.alter_column(
        "entity_relationship",
        "relationship_type",
        existing_type=sa.String(length=21),
        type_=sa.String(length=17),
        existing_nullable=False,
    )
