from pydantic import BaseModel, Field


class PostgresConfig(BaseModel):
    """Postgres configuration model."""

    database: str = Field(..., description="Postgres database name")
    username: str = Field(..., description="Postgres username")
    password: str = Field(..., description="Postgres password")
    host: str = Field(..., description="Postgres host for attaching to the logical cluster")
    port: int = Field(5432, description="Postgres port")
    pool_size: int = Field(10, description="Connection pool size")
    max_overflow: int = Field(20, description="Maximum overflow size for the pool")

    model_config = {
        "frozen": True,
    }
