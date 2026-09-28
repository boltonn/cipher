from abc import ABC, abstractmethod

from cipher.schemas.ingestion.dataset import Dataset
from cipher.schemas.ingestion.user import User, UserCreate, UserDatasetAccess, UserUpdate


class UserRepository(ABC):
    """Abstract base class for user repositories."""

    @abstractmethod
    async def create_user(self, user: UserCreate) -> User:
        """Create a new user."""
        pass

    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> User | None:
        """Retrieve user by ID."""
        pass

    @abstractmethod
    async def get_user_by_email(self, email: str) -> User | None:
        """Retrieve user by email."""
        pass

    @abstractmethod
    async def update_user(self, user_id: str, data: UserUpdate) -> User:
        """Update a user by ID."""
        pass

    @abstractmethod
    async def delete_user(self, user_id: str) -> bool:
        """Delete a user by ID."""
        pass

    @abstractmethod
    async def grant_dataset_access(
        self,
        user_id: str,
        dataset_id: str,
        granted_by: str | None,
        role: str,
    ) -> UserDatasetAccess:
        """Grant a user access to a dataset."""
        pass

    @abstractmethod
    async def revoke_dataset_access(self, user_id: str, dataset_id: str) -> bool:
        """Revoke a user's access to a dataset."""
        pass

    @abstractmethod
    async def get_user_datasets(self, user_id: str) -> list[Dataset]:
        """Get all datasets a user has access to."""
        pass

    @abstractmethod
    async def get_dataset_users(self, dataset_id: str) -> list[User]:
        """Get all users who have access to a dataset."""
        pass

    @abstractmethod
    async def has_dataset_access(self, user_id: str, dataset_id: str) -> bool:
        """Check if a user has access to a specific dataset."""
        pass
