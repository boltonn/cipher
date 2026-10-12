from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cipher.datastores.postgres.tables.base import Base


class DatasetProfileTable(Base):
    """Precomputed summary of a dataset -- what the empty-query search briefing shows.

    Full recompute by `cipher profile-dataset` after enrichment, so the briefing
    costs one row read at any corpus size. Dataset content: access-gated like
    chunks. See docs/global-search.md §6.
    """

    __tablename__ = "dataset_profile"

    dataset_id: Mapped[str] = mapped_column(String, ForeignKey("dataset.id", ondelete="CASCADE"), primary_key=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filetype_group_counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    language_counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    date_histogram: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    top_people_orgs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    top_selectors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    top_places: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    top_correspondents: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    image_sample_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    brief: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    date_computed: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
