import json
from pathlib import Path
from typing import Generic, TypeVar

from cipher.schemas.base import BaseModel
from cipher.schemas.common import PaginatedResponse


def load_mappings(path: Path) -> dict:
    """Load Elasticsearch index mappings from a JSON file."""
    with open(path) as f:
        return json.load(f)


T = TypeVar("T", bound=BaseModel)


class PaginatedResponse(PaginatedResponse, Generic[T]):
    data: list[T]


def paginate(
    data: list[T | dict],
    total: int,
    page: int,
    limit: int,
    model: type[T] | None = None,
) -> PaginatedResponse[T]:
    """Helper function to create a paginated response with optional model validation."""
    if model is not None:
        data = [
            model.model_validate(item) if isinstance(item, dict) else item
            for item in data
        ]
    return PaginatedResponse(
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit,
        data=data,
    )
