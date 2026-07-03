from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from cipher.schemas.common import ModelDevice
from cipher.utils.fastapi.settings import BaseServiceSettings


class Settings(BaseServiceSettings):
    """Face service settings model."""

    model_dir: Path = Field(
        ...,
        description="Path to HuggingFace text embedding model directory",
        alias="FACE_MODEL_DIR",
    )
    model_device: ModelDevice | None = Field(default=None, description="Device to use for the model")

    model_config = SettingsConfigDict(env_file=".env", protected_namespaces=[])
