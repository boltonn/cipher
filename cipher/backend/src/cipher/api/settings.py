from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import SettingsConfigDict

from cipher.datastores.elasticsearch.config import ElasticsearchConfig
from cipher.datastores.postgres.config import PostgresConfig
from cipher.schemas.interaction.llm import LLMSettings
from cipher.utils.fastapi.settings import BaseServiceSettings
from cipher.utils.retrieval import RetrievalBackend, RetrievalConfig, TextRanker

__all__ = ["Settings", "DevelopmentMode", "RetrievalBackend", "RetrievalConfig", "TextRanker"]


class DevelopmentMode(StrEnum):
    DEV = "development"
    PROD = "production"


class GithubConfig(BaseModel):
    """GitHub integration for filing dataset requests as issues.

    Populated from ``GITHUB__*`` env vars (nested delimiter is ``__``).
    Left unset, the dataset-request endpoints report themselves unconfigured.
    """

    repo: str = Field(..., description="owner/repo that receives dataset-request issues")
    token: str = Field(..., description="GitHub token with issues:write on the repo")
    api_base: str = Field("https://api.github.com", description="GitHub REST API base URL")
    labels: list[str] = Field(
        default_factory=lambda: ["dataset-request"],
        description="Labels applied to every dataset-request issue",
    )
    issue_type: str | None = Field(None, description="GitHub issue type name, if the org has issue types enabled")


class Settings(BaseServiceSettings):
    """Cipher service settings model."""

    github: GithubConfig | None = Field(None, description="GitHub integration for dataset requests")

    llm: LLMSettings = Field(default_factory=LLMSettings, description="Chat agent model configuration (LLM__* env vars)")

    elasticsearch: ElasticsearchConfig | None = Field(None, description="Elasticsearch configuration object")
    postgres: PostgresConfig | None = Field(None, description="Postgres configuration object")
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig, description="Chunk-search backend selection")
    mode: DevelopmentMode = Field(DevelopmentMode.DEV, description="Development mode")
    person_reference_dir: Path = Field(
        ...,
        description="Local directory where uploaded person reference photos are stored",
        alias="PERSON_REFERENCE_DIR",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="allow")
