from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, ColumnElement, DateTime, ForeignKey, Index, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import JSONB, array
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cipher.datastores.postgres.tables.base import Base

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.contact import ContactTable
    from cipher.datastores.postgres.tables.dataset import DatasetTable
    from cipher.datastores.postgres.tables.extracted_text import ExtractedTextTable


class FileTable(Base):
    """File Table model representing the 'file' table in PostgreSQL using SQLModel."""

    __tablename__ = "file"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    date_created: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_loaded: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    dataset_id: Mapped[str] = mapped_column(
        String, ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device: Mapped[str | None] = mapped_column(String, nullable=True)
    filename: Mapped[str] = mapped_column(String, nullable=False, index=True)
    filetype_group: Mapped[str] = mapped_column(String, nullable=False)
    filetype: Mapped[str] = mapped_column(String, nullable=False)
    filetype_name: Mapped[str | None] = mapped_column(String, nullable=True)
    md5: Mapped[str] = mapped_column(String, nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False, index=True)
    sha256: Mapped[str] = mapped_column(String, nullable=False, index=True)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uri: Mapped[str] = mapped_column(String, nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("file.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Labels for training classifiers over this file's embeddings: `tags` says "is this",
    # `negative_tags` says "is explicitly not this" (a hard negative). A tag is in at most one.
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    negative_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # A model's confidence that a tag applies ({tag: 0-1}) -- a prediction, kept apart from the labels above.
    tag_scores: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    # From the data, not a decision: copied from the extracted-text metadata on every extraction upsert.
    source_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    message_states: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # Found compressed (`CompressionInfo`): the encoding plus the as-found bytes' hashes and size.
    compression: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Tabular files: each sheet's layout (`TableSheetLayout`); null until `cipher map-tables` has profiled it.
    table_sheets: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)

    # Relationships (only defined if dependencies are available)
    dataset: Mapped["DatasetTable"] = relationship(back_populates="files")
    contacts: Mapped[list["ContactTable"]] = relationship(
        back_populates="file", cascade="all, delete-orphan", lazy="select"
    )
    extracted_text: Mapped["ExtractedTextTable | None"] = relationship(
        back_populates="file",
        uselist=False,
        cascade="all, delete-orphan",
        single_parent=True,
    )

    __table_args__ = (
        # One row per place a file was found; many rows may share a `uri` (content-addressed blobs).
        UniqueConstraint("dataset_id", "path", name="uq_dataset_path"),
        # Index for finding duplicates across datasets
        Index("ix_file_sha256_dataset", "sha256", "dataset_id"),
        Index("ix_file_tags_gin", "tags", postgresql_using="gin"),
        Index("ix_file_negative_tags_gin", "negative_tags", postgresql_using="gin"),
        Index("ix_file_source_tags_gin", "source_tags", postgresql_using="gin"),
        Index("ix_file_message_states_gin", "message_states", postgresql_using="gin"),
        Index(
            "ix_file_table_sheets_gin",
            "table_sheets",
            postgresql_using="gin",
            postgresql_ops={"table_sheets": "jsonb_path_ops"},
        ),
        Index("ix_file_filename_trgm", "filename", postgresql_using="gin", postgresql_ops={"filename": "gin_trgm_ops"}),
    )


def outside_source_tags(file_id: ColumnElement[str], tags: list[str]) -> ColumnElement[bool]:
    """SQL test that the file behind ``file_id`` carries none of these source tags (any-of exclude).

    A row with no file (``file_id`` NULL) passes.
    """
    return ~(select(FileTable.id).where(FileTable.id == file_id, FileTable.source_tags.has_any(array(tags))).exists())
