from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from cipher.schemas._base.common import ModelDevice
from cipher.utils.fastapi.settings import BaseServiceSettings


class Settings(BaseServiceSettings):
    """CLIR service settings model."""

    model_dir: Path = Field(
        ...,
        description="Path to HuggingFace text embedding model directory",
        alias="TEXT_EMBEDDING_MODEL_DIR",
    )
    max_batch_size: int = Field(
        1, description="Maximum batch size for batching", ge=1, alias="TEXT_EMBEDDING_MAX_BATCH_SIZE"
    )
    batch_timeout: float = Field(
        0, description="Timeout for batching in seconds", ge=0, alias="TEXT_EMBEDDING_BATCH_TIMEOUT"
    )
    model_device: ModelDevice | None = Field(
        None, description="Device to use for the model", alias="TEXT_EMBEDDING_MODEL_DEVICE"
    )

    model_config = SettingsConfigDict(env_file=".env", protected_namespaces=[])
