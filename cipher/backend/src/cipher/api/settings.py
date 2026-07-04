from enum import StrEnum
from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from cipher.datastores.elasticsearch.config import ElasticsearchConfig
from cipher.datastores.postgres.config import PostgresConfig
from cipher.utils.fastapi.settings import BaseServiceSettings


class DevelopmentMode(StrEnum):
    DEV = "development"
    PROD = "production"


class Settings(BaseServiceSettings):
    """Cipher service settings model."""

    elasticsearch: ElasticsearchConfig | None = Field(
        None, description="Elasticsearch configuration object"
    )
    postgres: PostgresConfig | None = Field(
        None, description="Postgres configuration object"
    )
    mode: DevelopmentMode = Field(DevelopmentMode.DEV, description="Development mode")
    person_reference_dir: Path = Field(
        ...,
        description="Local directory where uploaded person reference photos are stored",
        alias="PERSON_REFERENCE_DIR",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="allow")
