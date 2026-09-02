"""Abstract repositories base classes."""

from abc import ABC, abstractmethod

from cipher.schemas.ingestion.file import File, FileInstance, FilesRequest


class FileRepository(ABC):
    """Abstract base class for datastores."""

    @abstractmethod
    async def add_file(self, file: File):
        """Add a file to the datastore."""
        pass

    @abstractmethod
    async def add_file_instance(self, instance: FileInstance):
        """Add a file instance to the datastore."""
        pass

    @abstractmethod
    async def get_file_instance_by_file_instance_id(self, file_instance_id: str):
        """Retrieve a file instance by its ID."""
        pass

    @abstractmethod
    async def get_file_instances(self, request: FilesRequest):
        """Retrieve file instances based on a request."""
        pass

    @abstractmethod
    async def delete_file_instance(self, file_instance_id: str):
        """Delete a file instance by its ID."""
        pass
