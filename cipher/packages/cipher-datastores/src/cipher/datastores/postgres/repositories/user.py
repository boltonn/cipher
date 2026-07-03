"""User repository - encapsulates all database operations for users."""

from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.dataset import DatasetTable
from cipher.datastores.postgres.tables.user import UserTable
from cipher.schemas.user import User, UserCreate, UserUpdate


class PostgresUserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_data: UserCreate) -> User:
        """Create a new user."""
        data = user_data.model_dump()
        user_table = UserTable(**data)

        self.session.add(user_table)
        await self.session.commit()
        await self.session.refresh(user_table)

        return User.model_validate(user_table)

    async def get_by_id(self, user_id: str) -> User | None:
        """Get a user by ID."""
        result = await self.session.execute(
            select(UserTable).where(UserTable.id == user_id)
        )
        user_table = result.scalar_one_or_none()
        return User.model_validate(user_table) if user_table else None

    async def get_by_email(self, email: str) -> User | None:
        """Get a user by email."""
        result = await self.session.execute(
            select(UserTable).where(UserTable.email == email)
        )
        user_table = result.scalar_one_or_none()
        return User.model_validate(user_table) if user_table else None

    async def update(self, user_id: str, user_data: UserUpdate) -> User | None:
        """Update a user."""
        from datetime import UTC, datetime

        data = user_data.model_dump(exclude_unset=True)
        data["date_updated"] = datetime.now(UTC)

        stmt = (
            update(UserTable)
            .where(UserTable.id == user_id)
            .values(**data)
            .returning(UserTable)
        )

        result = await self.session.execute(stmt)
        await self.session.commit()

        user_table = result.scalar_one_or_none()
        return User.model_validate(user_table) if user_table else None

    async def delete(self, user_id: str) -> bool:
        """Delete a user by ID. Returns True if deleted, False if not found."""
        result = await self.session.execute(
            delete(UserTable).where(UserTable.id == user_id)
        )
        await self.session.commit()
        return (result.rowcount or 0) > 0

    async def list(
        self,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> list[User]:
        """List users with pagination."""
        result = await self.session.execute(
            select(UserTable)
            .order_by(UserTable.date_created.desc())
            .limit(limit)
            .offset(offset)
        )
        return [User.model_validate(user) for user in result.scalars().all()]

    async def count(self) -> int:
        """Count total users."""
        result = await self.session.execute(select(func.count(UserTable.id)))
        return result.scalar_one()

    async def exists(self, user_id: str) -> bool:
        """Check if a user exists."""
        result = await self.session.execute(
            select(func.count(UserTable.id)).where(UserTable.id == user_id)
        )
        return result.scalar_one() > 0

    # User-Dataset Access Methods (simplified - no roles)

    async def grant_dataset_access(self, user_id: str, dataset_id: str) -> bool:
        """Grant a user access to a dataset. Returns True if granted."""
        user = await self.session.get(UserTable, user_id)
        dataset = await self.session.get(DatasetTable, dataset_id)

        if not user or not dataset:
            return False

        if user not in dataset.users:
            dataset.users.append(user)
            await self.session.commit()

        return True

    async def revoke_dataset_access(self, user_id: str, dataset_id: str) -> bool:
        """Revoke a user's access to a dataset. Returns True if revoked."""
        user = await self.session.get(UserTable, user_id)
        dataset = await self.session.get(DatasetTable, dataset_id)

        if not user or not dataset:
            return False

        if user in dataset.users:
            dataset.users.remove(user)
            await self.session.commit()
            return True

        return False

    async def get_user_datasets(self, user_id: str) -> list[str]:
        """Get all dataset IDs that a user has access to."""
        user = await self.session.get(UserTable, user_id)
        if not user:
            return []
        return [dataset.id for dataset in user.datasets]

    async def get_dataset_users(self, dataset_id: str) -> list[User]:
        """Get all users who have access to a dataset."""
        dataset = await self.session.get(DatasetTable, dataset_id)
        if not dataset:
            return []
        return [User.model_validate(user) for user in dataset.users]

    async def has_dataset_access(self, user_id: str, dataset_id: str) -> bool:
        """Check if a user has access to a dataset."""
        user = await self.session.get(UserTable, user_id)
        if not user:
            return False
        return any(dataset.id == dataset_id for dataset in user.datasets)
