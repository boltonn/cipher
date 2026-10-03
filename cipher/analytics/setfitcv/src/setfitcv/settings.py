from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from cipher.schemas._base.common import ModelDevice
from cipher.utils.fastapi.settings import BaseServiceSettings


class Settings(BaseServiceSettings):
    """SetFitCV service settings model."""

    model_dir: Path = Field(
        ...,
        description="Path to HuggingFace image embedding model directory",
        alias="IMAGE_EMBEDDING_MODEL_DIR",
    )
    max_batch_size: int = Field(
        default=1, description="Maximum batch size for batching", alias="IMAGE_EMBEDDING_MAX_BATCH_SIZE"
    )
    batch_timeout: float = Field(
        default=0, description="Timeout for batching in seconds", alias="IMAGE_EMBEDDING_BATCH_TIMEOUT"
    )
    device: ModelDevice | None = Field(
        default=None, description="Device to use for the model", alias="IMAGE_EMBEDDING_MODE_DEVICE"
    )
    heads_dir: Path | None = Field(
        default=None, description="Trained tag heads (`heads.safetensors` + `heads.json`)", alias="IMAGE_HEADS_DIR"
    )
    classify: bool = Field(
        default=False,
        description="Score every image with the tag heads during inference (needs IMAGE_HEADS_DIR)",
        alias="IMAGE_CLASSIFY",
    )

    model_config = SettingsConfigDict(env_file=".env", protected_namespaces=[])
