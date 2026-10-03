from enum import StrEnum

from pydantic import Field

from cipher.schemas._base.base import BaseModel


class TableScope(StrEnum):
    """How a table's rows are attributed to a dataset."""

    DATASET = "dataset"  # its own dataset_id column
    FILE = "file"  # through file_id -> file.dataset_id
    SHARED = "shared"  # content-addressed or global, not attributable to one dataset


class TableMetrics(BaseModel):
    """One table's on-disk footprint."""

    name: str
    scope: TableScope
    total_bytes: int = Field(description="Table + indexes + TOAST")
    index_bytes: int
    row_count: int | None = Field(default=None, description="Planner estimate; null until the table is analyzed")


class DatasetTableUsage(BaseModel):
    """A dataset's rows in one table; bytes are the dataset's row share of the table's size."""

    table_name: str
    row_count: int
    estimated_bytes: int
    estimated_index_bytes: int


class DatasetDatabaseUsage(BaseModel):
    """How much of the database one dataset accounts for."""

    dataset_id: str
    dataset_name: str
    row_count: int
    estimated_bytes: int
    estimated_index_bytes: int
    tables: list[DatasetTableUsage] = Field(default_factory=list, description="Largest first")


class DatabaseMetrics(BaseModel):
    """Database size, every table's footprint, and an estimated breakdown by dataset."""

    database_size_bytes: int
    tables: list[TableMetrics] = Field(default_factory=list, description="Largest first")
    datasets: list[DatasetDatabaseUsage] = Field(default_factory=list, description="Largest first")
