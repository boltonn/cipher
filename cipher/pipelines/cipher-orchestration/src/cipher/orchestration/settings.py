from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from cipher.datastores.elasticsearch.config import ElasticsearchConfig
from cipher.datastores.postgres.config import PostgresConfig
from cipher.orchestration.image_size import DEFAULT_MIN_IMAGE_SIDE
from cipher.schemas._base.common import ModelDevice
from cipher.utils.fastapi.settings import BaseServiceSettings
from cipher.utils.output import OutputStore
from cipher.utils.retrieval import RetrievalConfig
from cipher.utils.search import SearchConfig


class Settings(BaseServiceSettings):
    """Orchestration settings: the CLI's defaults, overridable per run with its options.

    Model dirs and devices use the same env names as the analytic services, so one `.env` configures both.
    """

    postgres: PostgresConfig | None = Field(None, description="Postgres configuration object")
    elasticsearch: ElasticsearchConfig | None = Field(None, description="Elasticsearch configuration object")
    retrieval: RetrievalConfig = Field(
        default_factory=RetrievalConfig, description="Chunk-search backend (RETRIEVAL__*)"
    )
    search: SearchConfig = Field(default_factory=SearchConfig, description="Global search (SEARCH__*)")

    text_embedding_model_dir: Path | None = Field(default=None, alias="TEXT_EMBEDDING_MODEL_DIR")
    text_embedding_model_device: ModelDevice = Field(default=ModelDevice.CPU, alias="TEXT_EMBEDDING_MODEL_DEVICE")
    image_embedding_model_dir: Path | None = Field(default=None, alias="IMAGE_EMBEDDING_MODEL_DIR")
    image_embedding_model_device: ModelDevice = Field(default=ModelDevice.CPU, alias="IMAGE_EMBEDDING_MODEL_DEVICE")
    image_heads_dir: Path | None = Field(default=None, alias="IMAGE_HEADS_DIR")
    min_image_side: int = Field(default=DEFAULT_MIN_IMAGE_SIDE, alias="MIN_IMAGE_SIDE")
    face_model_dir: Path | None = Field(default=None, alias="FACE_MODEL_DIR")
    face_model_device: ModelDevice = Field(default=ModelDevice.CPU, alias="FACE_MODEL_DEVICE")
    easyocr_model_dir: Path | None = Field(default=None, alias="EASYOCR_MODEL_DIR")
    gliner_model_dir: str | None = Field(default=None, alias="GLINER_MODEL_DIR")
    gliner_model_device: ModelDevice = Field(default=ModelDevice.CPU, alias="GLINER_MODEL_DEVICE")
    nerd_model_dir: str | None = Field(default=None, alias="NERD_MODEL_DIR")
    nerd_model_device: ModelDevice = Field(default=ModelDevice.CPU, alias="NERD_MODEL_DEVICE")
    pytabular_gliner_url: str | None = Field(default=None, alias="PYTABULAR_GLINER_URL")
    pytabular_nerd_url: str | None = Field(default=None, alias="PYTABULAR_NERD_URL")
    output_uri: str = Field(
        default="~/data/cipher/output",
        alias="OUTPUT_URI",
        description="Where Cipher writes files it creates (archive members, attachments): a directory or "
        "s3://bucket/prefix; each dataset writes under <OUTPUT_URI>/<dataset_id>/ unless a step is given --output-uri",
    )
    archive_passwords_file: Path = Field(
        default=Path("~/data/cipher/archive-passwords.txt"),
        alias="ARCHIVE_PASSWORDS_FILE",
        description="Passwords to try on encrypted archive members, one per line (keep it readable only by you)",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="allow", populate_by_name=True, env_ignore_empty=True)


settings = Settings()


def output_store(*, dataset_id: str, output_uri: str | None = None) -> OutputStore:
    """Where a step writes the files it creates: `output_uri` as given, else `<OUTPUT_URI>/<dataset_id>/`."""
    return OutputStore(output_uri or f"{settings.output_uri.rstrip('/')}/{dataset_id}")
