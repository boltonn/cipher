"""Fold `person` comments into `entity` comments.

A person's bridge entity shares its id (`entity.id == person.id`), so the person page
and the entity page were showing two separate threads for one person. `entity` now
covers every entity type; the column stores enum member names (`native_enum=False`).

Revision ID: 0035_comment_person_to_entity
Revises: 0034_user_dataset_access
Create Date: 2026-10-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0035_comment_person_to_entity"
down_revision: str | None = "0034_user_dataset_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Re-point person comments at the person's bridge entity (same id); a no-op without a `comment` table."""
    op.execute(
        """
        DO $$ BEGIN
            IF to_regclass('comment') IS NOT NULL THEN
                UPDATE comment SET commentable_type = 'ENTITY' WHERE commentable_type = 'PERSON';
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    """Irreversible: person and entity comments are indistinguishable once folded."""
