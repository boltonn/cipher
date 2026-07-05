from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cipher.datastores.postgres.tables.base import Base

if TYPE_CHECKING:
    from cipher.datastores.postgres.tables.file import FileTable


class ExtractedTextTable(Base):
    """Canonical extracted text + structure for a file -- one row per file.

    This is the Stage-1 output of the text-extraction pipeline: the
    expensive-to-produce result of parsing/OCR, persisted once so chunking,
    embedding, or future entity extraction never need to re-run extraction.
    """

    __tablename__ = "extracted_text"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    file_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("file.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_format: Mapped[str] = mapped_column(String, nullable=False, default="plain")
    extractor: Mapped[str] = mapped_column(String, nullable=False)

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    prechunked: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    date_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    date_last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    file: Mapped["FileTable"] = relationship(back_populates="extracted_text")
