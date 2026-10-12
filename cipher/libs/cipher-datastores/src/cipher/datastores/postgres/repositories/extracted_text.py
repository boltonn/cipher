from datetime import datetime
from typing import Final

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.extracted_text import ExtractedTextTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.utils import strip_null_bytes
from cipher.schemas.content.email import ConversationEmail
from cipher.schemas.content.extraction import ExtractedText, ExtractedTextCreate

_MAX_CONVERSATION_TEXT_CHARS: Final[int] = 20_000
_MAX_CONVERSATION_EMAILS: Final[int] = 500


def _to_schema(row: ExtractedTextTable) -> ExtractedText:
    """Validate an ORM row into `ExtractedText`.

    The `metadata` column is mapped to the Python attribute `metadata_`
    (SQLAlchemy reserves `metadata` on declarative models for the table
    registry), so it's remapped back to `metadata` here rather than via
    `from_attributes` on the row directly.
    """
    return ExtractedText.model_validate({**row.__dict__, "metadata": row.metadata_})


class PostgresExtractedTextRepository:
    """Postgres datastore implementation using SQLAlchemy."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the extracted_text table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(ExtractedTextTable.metadata.create_all)

    async def get_by_file_id(self, file_id: str) -> ExtractedText | None:
        """Retrieve the extracted text for a file, if it's been extracted."""
        result = await self.session.execute(select(ExtractedTextTable).where(ExtractedTextTable.file_id == file_id))
        row = result.scalar_one_or_none()
        return _to_schema(row) if row else None

    async def get_by_file_ids(self, file_ids: list[str]) -> dict[str, ExtractedText]:
        """Extracted text keyed by file id, for the subset of `file_ids` that have been extracted."""
        if not file_ids:
            return {}
        result = await self.session.execute(select(ExtractedTextTable).where(ExtractedTextTable.file_id.in_(file_ids)))
        return {row.file_id: _to_schema(row) for row in result.scalars().all()}

    async def get_email_copies(
        self, meaningful_hash: str, exclude_file_id: str, dataset_ids: frozenset[str] | None
    ) -> list[str]:
        """Other email files with this meaningful hash (the same message), limited to `dataset_ids` (None: all)."""
        query = (
            select(ExtractedTextTable.file_id)
            .join(FileTable, FileTable.id == ExtractedTextTable.file_id)
            .where(
                ExtractedTextTable.metadata_.has_key("meaningful_hash"),
                ExtractedTextTable.metadata_["meaningful_hash"].astext == meaningful_hash,
                ExtractedTextTable.file_id != exclude_file_id,
            )
            .order_by(ExtractedTextTable.file_id)
        )
        if dataset_ids is not None:
            query = query.where(FileTable.dataset_id.in_(dataset_ids))
        return list((await self.session.scalars(query)).all())

    async def get_conversation_emails(
        self, conversation_id: str, file_id: str, dataset_ids: frozenset[str] | None
    ) -> list[tuple[ConversationEmail, str]]:
        """The emails sharing `conversation_id` in `dataset_ids` (None: all), each with its text.

        One per message: copies (same meaningful hash or Message-ID) are listed once, preferring `file_id`.
        """
        return await self._conversation_rows(
            condition="t.metadata ? 'conversation_id' AND t.metadata->>'conversation_id' = :conversation_id",
            params={"conversation_id": conversation_id, "file_id": file_id},
            dataset_ids=dataset_ids,
        )

    async def get_subject_candidates(
        self, subject_key: str, file_id: str, date_from: datetime, date_to: datetime, dataset_id: str
    ) -> list[tuple[ConversationEmail, str]]:
        """Emails in `dataset_id` sent between the dates whose subject contains `subject_key`, each with its text.

        A loose pre-filter: callers compare the full subject key and check the quotes.
        """
        return await self._conversation_rows(
            condition="f.filetype_group = 'email' AND strpos(lower(t.metadata->>'title'), :subject_key) > 0 "
            "AND (t.metadata->>'date_sent')::timestamptz BETWEEN :date_from AND :date_to",
            params={"subject_key": subject_key, "file_id": file_id, "date_from": date_from, "date_to": date_to},
            dataset_ids=frozenset({dataset_id}),
        )

    async def _conversation_rows(
        self, condition: str, params: dict, dataset_ids: frozenset[str] | None
    ) -> list[tuple[ConversationEmail, str]]:
        scope = "" if dataset_ids is None else "AND f.dataset_id = ANY(:dataset_ids)"
        message_key = "coalesce(t.metadata->>'meaningful_hash', t.metadata->>'message_id', t.file_id)"
        query = text(
            f"""
            SELECT DISTINCT ON ({message_key})
                t.file_id, t.metadata->>'title' AS title,
                t.metadata->'sent_from'->>'name' AS from_name, t.metadata->'sent_from'->>'value' AS from_address,
                (t.metadata->>'date_sent')::timestamptz AS date_sent, left(t.content, :max_chars) AS content
            FROM extracted_text t JOIN file f ON f.id = t.file_id
            WHERE {condition} {scope}
            ORDER BY {message_key}, t.file_id = :file_id DESC, t.file_id
            LIMIT :limit
            """
        )
        bound = {**params, "max_chars": _MAX_CONVERSATION_TEXT_CHARS, "limit": _MAX_CONVERSATION_EMAILS}
        if dataset_ids is not None:
            bound["dataset_ids"] = list(dataset_ids)
        rows = (await self.session.execute(query, bound)).mappings().all()
        emails = [
            (
                ConversationEmail(
                    file_id=row["file_id"],
                    title=row["title"],
                    from_name=row["from_name"],
                    from_address=row["from_address"],
                    date_sent=row["date_sent"],
                ),
                row["content"] or "",
            )
            for row in rows
        ]
        return sorted(emails, key=lambda pair: (pair[0].date_sent is None, pair[0].date_sent or datetime.min))

    async def get_file_ids_with_text(self, file_ids: list[str]) -> set[str]:
        """The subset of `file_ids` that already have an extraction row."""
        if not file_ids:
            return set()
        result = await self.session.execute(
            select(ExtractedTextTable.file_id).where(ExtractedTextTable.file_id.in_(file_ids))
        )
        return set(result.scalars().all())

    async def upsert(self, extracted: ExtractedTextCreate) -> ExtractedText:
        """Upsert extracted text -- insert or overwrite if file_id already has a row.

        A text an analyst corrected (`is_content_corrected`) is never overwritten; the stored row comes back.
        Also refreshes the file's `source_tags` / `message_states`, the filterable copy of what the metadata says.
        """
        data = strip_null_bytes(extracted.model_dump(mode="json"))
        data["metadata_"] = data.pop("metadata")  # ORM attribute name; see `_to_schema`

        stmt = pg_insert(ExtractedTextTable).values(**data)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["file_id"],
            set_={
                "content": stmt.excluded.content,
                "content_format": stmt.excluded.content_format,
                "extractor": stmt.excluded.extractor,
                "metadata": stmt.excluded.metadata,
                "prechunked": stmt.excluded.prechunked,
                "is_content_corrected": stmt.excluded.is_content_corrected,
                "content_corrected_by": stmt.excluded.content_corrected_by,
                "corrected_ranges": stmt.excluded.corrected_ranges,
            },
            where=ExtractedTextTable.is_content_corrected.is_(False),
        ).returning(ExtractedTextTable)

        row = (await self.session.execute(upsert_stmt)).scalar_one_or_none()
        if row is None:
            await self.session.commit()
            return await self.get_by_file_id(extracted.file_id)
        await self.session.execute(
            update(FileTable)
            .where(FileTable.id == extracted.file_id)
            .values(source_tags=extracted.source_tags(), message_states=extracted.message_states())
        )
        await self.session.commit()
        return _to_schema(row)

    async def delete_by_file_id(self, file_id: str) -> bool:
        """Delete the extracted text for a file, if present."""
        result = await self.session.execute(select(ExtractedTextTable).where(ExtractedTextTable.file_id == file_id))
        row = result.scalar_one_or_none()
        if row is None:
            return False

        await self.session.delete(row)
        await self.session.commit()
        return True
