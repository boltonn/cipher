"""Let reviewed face-match decisions outlive their person.

`face_match.person_id` loses its cascading FK: deleting a person used to delete
every confirmed / rejected decision made about it. The id now stays as the key
that groups those faces (pending matches are dropped by the delete itself).
Manual assignments are backfilled as confirmed matches, so `face_match` holds
every manual decision, and assignment metadata left on unlinked faces is cleared.

Revision ID: 0029_face_match_outlives_person
Revises: 0028_text_mentions_corrected
Create Date: 2026-10-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029_face_match_outlives_person"
down_revision: str | None = "0028_text_mentions_corrected"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("face_match_person_id_fkey", "face_match", type_="foreignkey")
    op.execute(
        """
        INSERT INTO face_match (id, face_id, person_id, similarity_score, match_method, status, date_created)
        SELECT gen_random_uuid()::text, id, person_id, coalesce(assignment_confidence, 0), 'MANUAL', 'CONFIRMED', now()
        FROM face WHERE person_id IS NOT NULL AND assignment_method = 'MANUAL'
        ON CONFLICT ON CONSTRAINT uq_face_match_face_person DO UPDATE SET status = 'CONFIRMED'
        """
    )
    op.execute(
        "UPDATE face SET assignment_method = NULL, assignment_confidence = NULL "
        "WHERE person_id IS NULL AND assignment_method IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DELETE FROM face_match WHERE person_id NOT IN (SELECT id FROM person)")
    op.create_foreign_key(
        "face_match_person_id_fkey", "face_match", "person", ["person_id"], ["id"], ondelete="CASCADE"
    )
