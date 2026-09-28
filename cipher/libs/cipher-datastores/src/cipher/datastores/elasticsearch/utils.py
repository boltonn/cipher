import json
from pathlib import Path

from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import PaginatedResponse


def load_mappings(path: Path) -> dict:
    """Load Elasticsearch index mappings from a JSON file."""
    with open(path) as f:
        return json.load(f)


class PaginatedResponse[T: BaseModel](PaginatedResponse):
    data: list[T]


def paginate[T: BaseModel](
    data: list[T | dict],
    total: int,
    page: int,
    limit: int,
    model: type[T] | None = None,
) -> PaginatedResponse[T]:
    """Helper function to create a paginated response with optional model validation."""
    if model is not None:
        data = [model.model_validate(item) if isinstance(item, dict) else item for item in data]
    return PaginatedResponse(
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit,
        data=data,
    )
