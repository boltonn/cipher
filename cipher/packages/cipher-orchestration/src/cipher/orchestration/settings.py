from pydantic import Field
from pydantic_settings import SettingsConfigDict

from cipher.datastores.postgres.config import PostgresConfig
from cipher.utils.fastapi.settings import BaseServiceSettings


class Settings(BaseServiceSettings):
    """Orchestration settings."""

    postgres: PostgresConfig | None = Field(
        None, description="Postgres configuration object"
    )
    model_config = SettingsConfigDict(env_file=".env", extra="allow")
