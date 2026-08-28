from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.extracted_text import ExtractedTextTable
from cipher.datastores.postgres.utils import strip_null_bytes
from cipher.schemas.extraction import ExtractedText, ExtractedTextCreate


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
        result = await self.session.execute(
            select(ExtractedTextTable).where(ExtractedTextTable.file_id == file_id)
        )
        row = result.scalar_one_or_none()
        return _to_schema(row) if row else None

    async def upsert(self, extracted: ExtractedTextCreate) -> ExtractedText:
        """Upsert extracted text -- insert or overwrite if file_id already has a row."""
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
            },
        ).returning(ExtractedTextTable)

        result = await self.session.execute(upsert_stmt)
        await self.session.commit()

        row = result.scalar_one()
        return _to_schema(row)

    async def delete_by_file_id(self, file_id: str) -> bool:
        """Delete the extracted text for a file, if present."""
        result = await self.session.execute(
            select(ExtractedTextTable).where(ExtractedTextTable.file_id == file_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False

        await self.session.delete(row)
        await self.session.commit()
        return True
