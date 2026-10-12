import secrets
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base

_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"


def new_search_id() -> str:
    """Opaque, URL-safe id (`s_` + 12 base32 chars) -- carries nothing about the query."""
    return "s_" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(12))


class SearchTable(Base):
    """A stored question -- query, datasets, filters -- never its results.

    Opening a search re-runs it. Upserted on `fingerprint` so re-asking the same
    question bumps `run_count` instead of growing the table. Private to `user_id`
    (admins can read any). Unsaved rows are pruned after a short retention
    window; a saved search has `date_saved`. See docs/global-search.md §7.
    """

    __tablename__ = "search"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_search_id)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)

    query: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dataset_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    parent_id: Mapped[str | None] = mapped_column(String, ForeignKey("search.id", ondelete="SET NULL"), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    llm_plan: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    date_last_run: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    date_saved: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_search_user_last_run", "user_id", date_last_run.desc()),
        Index("ix_search_unsaved_last_run", "date_last_run", postgresql_where=date_saved.is_(None)),
    )
