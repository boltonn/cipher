"""User repository - users plus their dataset memberships."""

from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.dataset import DatasetTable
from cipher.datastores.postgres.tables.user import UserDatasetAccessTable, UserTable
from cipher.schemas._base.exceptions import EntityAlreadyExistsError
from cipher.schemas.ingestion.user import PaginatedUsersResponse, User, UserCreate, UsersRequest, UserUpdate


class PostgresUserRepository:
    """Postgres datastore for users and `user_dataset_access` membership."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user: UserCreate) -> User:
        """Create a new user; raises if the email is taken."""
        if await self.get_by_email(email=user.email) is not None:
            raise EntityAlreadyExistsError(f"User already exists: {user.email}")
        user_table = UserTable(**user.model_dump())
        self.session.add(user_table)
        await self.session.commit()
        return User.model_validate(user_table)

    async def get_or_create(self, user: UserCreate) -> User:
        """Return the user with this email, creating it if missing (for entitlement syncs and dev bootstrap)."""
        existing = await self.get_by_email(email=user.email)
        return existing if existing is not None else await self.create(user=user)

    async def get_by_id(self, user_id: str) -> User | None:
        """Get a user by ID."""
        user_table = await self.session.get(UserTable, user_id)
        return User.model_validate(user_table) if user_table else None

    async def get_by_email(self, email: str) -> User | None:
        """Get a user by email (case-insensitive)."""
        result = await self.session.execute(select(UserTable).where(func.lower(UserTable.email) == email.lower()))
        user_table = result.scalar_one_or_none()
        return User.model_validate(user_table) if user_table else None

    async def update(self, user_id: str, data: UserUpdate) -> User | None:
        """Update a user's provided fields; None if not found."""
        values = {**data.model_dump(exclude_unset=True), "date_updated": datetime.now(UTC)}
        result = await self.session.execute(
            update(UserTable).where(UserTable.id == user_id).values(**values).returning(UserTable)
        )
        await self.session.commit()
        user_table = result.scalar_one_or_none()
        return User.model_validate(user_table) if user_table else None

    async def delete(self, user_id: str) -> bool:
        """Delete a user by ID. Returns True if deleted, False if not found."""
        result = await self.session.execute(delete(UserTable).where(UserTable.id == user_id))
        await self.session.commit()
        return (result.rowcount or 0) > 0

    async def list_users(self, request: UsersRequest) -> PaginatedUsersResponse:
        """List users by name, optionally filtered by a name/email match."""
        where = []
        if request.query:
            where.append(or_(UserTable.name.ilike(f"%{request.query}%"), UserTable.email.ilike(f"%{request.query}%")))
        total = await self.session.scalar(select(func.count(UserTable.id)).where(*where))
        result = await self.session.execute(
            select(UserTable).where(*where).order_by(UserTable.name).offset(request.offset).limit(request.limit)
        )
        return PaginatedUsersResponse(
            total=total or 0,
            page=request.page,
            limit=request.limit,
            data=[User.model_validate(u) for u in result.scalars().all()],
        )

    # ---- dataset membership -------------------------------------------

    async def get_dataset_ids(self, user_id: str) -> list[str]:
        """IDs of the datasets a user is a member of (admins' implicit access not included)."""
        result = await self.session.execute(
            select(UserDatasetAccessTable.dataset_id).where(UserDatasetAccessTable.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_dataset_users(self, dataset_id: str) -> list[User]:
        """Members of a dataset, by name."""
        result = await self.session.execute(
            select(UserTable)
            .join(UserDatasetAccessTable, UserDatasetAccessTable.user_id == UserTable.id)
            .where(UserDatasetAccessTable.dataset_id == dataset_id)
            .order_by(UserTable.name)
        )
        return [User.model_validate(u) for u in result.scalars().all()]

    async def has_dataset_access(self, user_id: str, dataset_id: str) -> bool:
        """Whether a user is a member of a dataset."""
        row = await self.session.get(UserDatasetAccessTable, (user_id, dataset_id))
        return row is not None

    async def grant_dataset_access(self, user_id: str, dataset_ids: list[str]) -> None:
        """Add memberships (existing ones are kept as-is)."""
        if not dataset_ids:
            return
        await self.session.execute(
            pg_insert(UserDatasetAccessTable)
            .values([{"user_id": user_id, "dataset_id": dataset_id} for dataset_id in dataset_ids])
            .on_conflict_do_nothing()
        )
        await self.session.commit()

    async def revoke_dataset_access(self, user_id: str, dataset_ids: list[str]) -> bool:
        """Remove memberships. Returns True if any were removed."""
        result = await self.session.execute(
            delete(UserDatasetAccessTable).where(
                UserDatasetAccessTable.user_id == user_id, UserDatasetAccessTable.dataset_id.in_(dataset_ids)
            )
        )
        await self.session.commit()
        return (result.rowcount or 0) > 0

    async def set_dataset_access(self, user_id: str, dataset_ids: list[str]) -> list[str]:
        """Make a user's memberships exactly `dataset_ids` -- the entry point for an entitlement sync.

        IDs of datasets that don't exist here (not processed yet) are ignored, so a sync can pass
        everything the upstream source grants. Returns the membership as stored.
        """
        known = await self.session.execute(select(DatasetTable.id).where(DatasetTable.id.in_(dataset_ids)))
        wanted = set(known.scalars().all())
        current = set(await self.get_dataset_ids(user_id=user_id))
        if current - wanted:
            await self.revoke_dataset_access(user_id=user_id, dataset_ids=list(current - wanted))
        await self.grant_dataset_access(user_id=user_id, dataset_ids=list(wanted - current))
        return sorted(wanted)
