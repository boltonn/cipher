from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cipher.datastores.postgres.tables.base import Base

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.contact import ContactTable
    from cipher.datastores.postgres.tables.dataset import DatasetTable
    from cipher.datastores.postgres.tables.extracted_text import ExtractedTextTable
    from cipher.datastores.postgres.tables.image import ImageTable


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

    # Relationships (only defined if dependencies are available)
    dataset: Mapped["DatasetTable"] = relationship(back_populates="files")
    image: Mapped["ImageTable | None"] = relationship(
        back_populates="file",
        uselist=False,
        cascade="all, delete-orphan",
        single_parent=True,
    )
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
        # Prevent exact duplicates within a dataset
        UniqueConstraint("dataset_id", "uri", name="uq_dataset_uri"),
        # Index for finding duplicates across datasets
        Index("ix_file_sha256_dataset", "sha256", "dataset_id"),
    )
