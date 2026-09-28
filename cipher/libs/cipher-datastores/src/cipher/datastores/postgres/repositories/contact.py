from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.contact import ContactTable
from cipher.schemas.content.contact import Contact, ContactCreate


class PostgresContactRepository:
    """Postgres datastore implementation for Contacts using ParadeDB (BM25)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the contact table and initialize the ParadeDB BM25 index."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(ContactTable.metadata.create_all)

            await conn.execute(
                text("""
                CREATE INDEX IF NOT EXISTS idx_contact_search ON contact 
                USING bm25 (
                    id, 
                    first_name, 
                    last_name, 
                    full_name,
                    organization, 
                    note, 
                    emails, 
                    phone_numbers
                ) WITH (key_field='id');
            """)
            )

    async def get_count(self) -> int:
        """Get total count of contacts."""
        result = await self.session.execute(select(func.count(ContactTable.id)))
        return result.scalar_one()

    async def get_contact_by_id(self, contact_id: str) -> Contact | None:
        """Retrieve a contact by its ID."""
        result = await self.session.execute(select(ContactTable).where(ContactTable.id == contact_id))
        contact_table = result.scalar_one_or_none()
        return Contact.model_validate(contact_table) if contact_table else None

    async def upsert_contact(self, contact: ContactCreate) -> Contact:
        """Upsert a contact using PostgreSQL ON CONFLICT."""
        data = contact.model_dump()
        stmt = pg_insert(ContactTable).values(**data)

        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "address": stmt.excluded["address"],
                "date_of_birth": stmt.excluded["date_of_birth"],
                "emails": stmt.excluded["emails"],
                "first_name": stmt.excluded["first_name"],
                "full_name": stmt.excluded["full_name"],
                "last_name": stmt.excluded["last_name"],
                "note": stmt.excluded["note"],
                "organization": stmt.excluded["organization"],
                "phone_numbers": stmt.excluded["phone_numbers"],
                "file_id": stmt.excluded["file_id"],
                "device_id": stmt.excluded["device_id"],
                "date_created": stmt.excluded["date_created"],
            },
        ).returning(ContactTable)

        result = await self.session.execute(upsert_stmt)
        await self.session.commit()

        contact_table = result.scalar_one()
        return Contact.model_validate(contact_table)

    async def upsert_contact_batch(self, contacts: list[ContactCreate]) -> None:
        """Perform a high-performance batch upsert for contact ingestion."""
        if not contacts:
            return

        rows = [c.model_dump() for c in contacts]
        stmt = pg_insert(ContactTable).values(rows)

        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "address": stmt.excluded["address"],
                "date_of_birth": stmt.excluded["date_of_birth"],
                "emails": stmt.excluded["emails"],
                "first_name": stmt.excluded["first_name"],
                "full_name": stmt.excluded["full_name"],
                "last_name": stmt.excluded["last_name"],
                "note": stmt.excluded["note"],
                "organization": stmt.excluded["organization"],
                "phone_numbers": stmt.excluded["phone_numbers"],
                "file_id": stmt.excluded["file_id"],
                "device_id": stmt.excluded["device_id"],
                "date_created": stmt.excluded["date_created"],
            },
        )

        await self.session.execute(upsert_stmt)
        await self.session.commit()

        del rows

    async def search_contacts(self, query: str, limit: int = 20, offset: int = 0) -> list[Contact]:
        """Perform a global BM25 search across all contact fields using ParadeDB."""
        statement = select(ContactTable).where(text("contact @@@ :q")).params(q=query).limit(limit).offset(offset)

        result = await self.session.execute(statement)
        return [Contact.model_validate(c) for c in result.scalars().all()]

    async def delete_contact(self, contact_id: str) -> bool:
        """Delete a contact and commit the transaction."""
        result = await self.session.execute(delete(ContactTable).where(ContactTable.id == contact_id))
        await self.session.commit()
        return bool(result.rowcount)
