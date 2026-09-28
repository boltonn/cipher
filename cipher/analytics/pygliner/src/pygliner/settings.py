from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from cipher.schemas._base.common import ModelDevice
from cipher.utils.fastapi.settings import BaseServiceSettings


class Settings(BaseServiceSettings):
    """pygliner service settings."""

    model_dir: str = Field(
        default="~/models/gliner/gliner2.5-multi-v1",
        description="Local GLiNER2.5 checkpoint directory (loaded offline, no hub access)",
        alias="GLINER_MODEL_DIR",
    )
    model_device: ModelDevice | None = Field(
        default=None, description="Device to use for the model", alias="GLINER_MODEL_DEVICE"
    )

    model_config = SettingsConfigDict(env_file=".env", protected_namespaces=[])

    @property
    def resolved_model_dir(self) -> str:
        """Checkpoint directory with `~` expanded."""
        return str(Path(self.model_dir).expanduser())
