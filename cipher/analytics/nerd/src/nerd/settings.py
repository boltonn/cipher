from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from cipher.schemas.common import ModelDevice
from cipher.utils.fastapi.settings import BaseServiceSettings


class Settings(BaseServiceSettings):
    """nerd service settings."""

    model_dir: str = Field(
        ...,
        description="Local path or HuggingFace id of the token-classification model",
        alias="NERD_MODEL_DIR",
    )
    model_device: ModelDevice | None = Field(
        default=None, description="Device to use for the model", alias="NERD_MODEL_DEVICE"
    )
    aggregation_strategy: str = Field(
        default="first",
        description="HF pipeline span aggregation: none|simple|first|average|max",
        alias="NERD_AGGREGATION_STRATEGY",
    )

    model_config = SettingsConfigDict(env_file=".env", protected_namespaces=[])

    @property
    def resolved_model_dir(self) -> str:
        """Expand a filesystem path; leave a bare HuggingFace id untouched."""
        candidate = Path(self.model_dir).expanduser()
        return str(candidate) if candidate.exists() else self.model_dir
