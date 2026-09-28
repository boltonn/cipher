from pathlib import Path

from pydantic import BaseModel, Field


class ElasticsearchConfig(BaseModel):
    """Elasticsearch configuration model."""

    username: str = Field(..., description="Elasticsearch username")
    password: str = Field(..., description="Elasticsearch password")
    ca_cert: Path | None = Field(None, description="Path to the CA certificate for Elasticsearch")
    host: str = Field(..., description="Elasticsearch host for attaching to the logical cluster")
    port: int = Field(9200, description="Elasticsearch port")
