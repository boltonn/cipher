"""Abstract repositories base classes."""

from abc import ABC, abstractmethod


class DatasetRepository(ABC):
    """Abstract base class for datastores."""

    @abstractmethod
    async def add_dataset(self, dataset_base):
        """Add a dataset to the datastore."""
        pass

    @abstractmethod
    async def get_dataset_by_id(self, dataset_id: str):
        """Retrieve a dataset by its ID."""
        pass

    @abstractmethod
    async def get_datasets(self, request):
        """Retrieve datasets based on a request."""
        pass
