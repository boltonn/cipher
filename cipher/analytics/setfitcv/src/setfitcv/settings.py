from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from cipher.utils.fastapi.settings import BaseServiceSettings
from setfitcv.schemas import ModelDevice


class Settings(BaseServiceSettings):
    """SetFitCV service settings model."""

    model_dir: Path = Field(
        ...,
        description="Path to HuggingFace image embedding model directory",
        alias="IMAGE_EMBEDDING_MODEL_DIR",
    )
    max_batch_size: int = Field(1, description="Maximum batch size for batching")
    batch_timeout: float = Field(0, description="Timeout for batching in seconds")
    device: ModelDevice | None = Field(None, description="Device to use for the model")

    model_config = SettingsConfigDict(env_file=".env", protected_namespaces=[])
