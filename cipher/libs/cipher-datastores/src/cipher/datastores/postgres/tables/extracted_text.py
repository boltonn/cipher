from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, text
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
    # an email's other copies (`EmailMetadata.meaningful_hash`), for "same message as N other copies"
    __table_args__ = (
        Index(
            "ix_extracted_text_meaningful_hash",
            text("(metadata->>'meaningful_hash')"),
            postgresql_where=text("metadata ? 'meaningful_hash'"),
        ),
        # an email's conversation (`EmailMetadata.conversation_id`), for the email viewer's conversation list
        Index(
            "ix_extracted_text_conversation_id",
            text("(metadata->>'conversation_id')"),
            postgresql_where=text("metadata ? 'conversation_id'"),
        ),
    )

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
    # An analyst drew, relabelled, or deleted a mention in this text: its mentions are retraining material.
    is_mentions_corrected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    mentions_reviewed_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    # An analyst corrected the text itself (OCR mistakes) -- pipelines never overwrite it after that.
    is_content_corrected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    content_corrected_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    # `[start, end)` stretches of `content` a person wrote; re-run extractors only add mentions there.
    corrected_ranges: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    file: Mapped["FileTable"] = relationship(back_populates="extracted_text")
