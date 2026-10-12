"""Global search G0: `search` + `dataset_profile` tables, trigram name indexes.

`search` stores a question (query, datasets, filters), never its results, and
backs `/search/[searchId]` navigation and later saved searches/alerts.
`dataset_profile` is the precomputed briefing for an empty query. The trigram
indexes turn the overview's filename / event title / place name / person name
lanes from sequential scans into index scans. See docs/global-search.md.

Revision ID: 0042_global_search
Revises: 0041_relation_reviewed
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042_global_search"
down_revision: str | None = "0041_relation_reviewed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRGM_INDEXES = (
    ("ix_file_filename_trgm", "file", "filename"),
    ("ix_event_title_trgm", "event", "title"),
    ("ix_location_name_trgm", "location", "name"),
    ("ix_person_name_trgm", "person", "name"),
)
_EMPTY_LIST = sa.text("'[]'::jsonb")
_EMPTY_DICT = sa.text("'{}'::jsonb")


def upgrade() -> None:
    """Create the tables and indexes."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "search",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("query", sa.Text(), nullable=False, server_default=""),
        sa.Column("dataset_ids", postgresql.JSONB(), nullable=False, server_default=_EMPTY_LIST),
        sa.Column("filters", postgresql.JSONB(), nullable=False, server_default=_EMPTY_DICT),
        sa.Column("parent_id", sa.String(), sa.ForeignKey("search.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fingerprint", sa.String(), nullable=False, unique=True),
        sa.Column("llm_plan", postgresql.JSONB(), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("date_created", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("date_last_run", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("date_saved", sa.DateTime(timezone=True), nullable=True),
        if_not_exists=True,
    )
    op.create_index("ix_search_user_last_run", "search", ["user_id", sa.text("date_last_run DESC")], if_not_exists=True)
    op.create_index(
        "ix_search_unsaved_last_run",
        "search",
        ["date_last_run"],
        postgresql_where=sa.text("date_saved IS NULL"),
        if_not_exists=True,
    )

    op.create_table(
        "dataset_profile",
        sa.Column("dataset_id", sa.String(), sa.ForeignKey("dataset.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("profile_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("filetype_group_counts", postgresql.JSONB(), nullable=False, server_default=_EMPTY_DICT),
        sa.Column("language_counts", postgresql.JSONB(), nullable=False, server_default=_EMPTY_DICT),
        sa.Column("date_histogram", postgresql.JSONB(), nullable=False, server_default=_EMPTY_LIST),
        sa.Column("top_people_orgs", postgresql.JSONB(), nullable=False, server_default=_EMPTY_LIST),
        sa.Column("top_selectors", postgresql.JSONB(), nullable=False, server_default=_EMPTY_LIST),
        sa.Column("top_places", postgresql.JSONB(), nullable=False, server_default=_EMPTY_LIST),
        sa.Column("top_correspondents", postgresql.JSONB(), nullable=False, server_default=_EMPTY_LIST),
        sa.Column("image_sample_ids", postgresql.JSONB(), nullable=False, server_default=_EMPTY_LIST),
        sa.Column("brief", postgresql.JSONB(), nullable=True),
        sa.Column("date_computed", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        if_not_exists=True,
    )
    # CONCURRENTLY so a large live `file` table keeps taking ingest writes during the build.
    with op.get_context().autocommit_block():
        for name, table, column in _TRGM_INDEXES:
            op.create_index(
                name,
                table,
                [column],
                postgresql_using="gin",
                postgresql_ops={column: "gin_trgm_ops"},
                postgresql_concurrently=True,
                if_not_exists=True,
            )


def downgrade() -> None:
    """Drop the tables and indexes."""
    op.drop_table("dataset_profile", if_exists=True)
    op.drop_index("ix_search_unsaved_last_run", table_name="search", if_exists=True)
    op.drop_index("ix_search_user_last_run", table_name="search", if_exists=True)
    op.drop_table("search", if_exists=True)
    for name, table, _ in _TRGM_INDEXES:
        op.drop_index(name, table_name=table, if_exists=True)
