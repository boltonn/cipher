from importlib.metadata import metadata

from pydantic import BaseModel


class ServiceInfo(BaseModel):
    title: str
    version: str
    description: str


def get_package_info(name: str) -> ServiceInfo:
    """Get package info from metadata."""
    package = metadata(name)
    return ServiceInfo(
        title=package.get("Name"),
        version=package.get("Version"),
        description=package.get("Summary"),
    )
