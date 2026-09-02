from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from cipher.schemas._base.common import ModelDevice
from cipher.utils.fastapi.settings import BaseServiceSettings


def _resolve(model_dir: str) -> str:
    """Expand a filesystem path; leave a bare HuggingFace id untouched."""
    candidate = Path(model_dir).expanduser()
    return str(candidate) if candidate.exists() else model_dir


class Settings(BaseServiceSettings):
    """pygliner service settings."""

    model_dir: str = Field(
        default="urchade/gliner_multi-v2.1",
        description="Local path or HuggingFace id of the GLiNER (entity) model",
        alias="NER_MODEL_DIR",
    )
    relation_model_dir: str = Field(
        default="jackboyla/glirel-large-v0",
        description="Local path or HuggingFace id of the GLiREL (relation) model",
        alias="RELATION_MODEL_DIR",
    )
    model_device: ModelDevice | None = Field(
        default=None, description="Device to use for the models", alias="NER_MODEL_DEVICE"
    )

    model_config = SettingsConfigDict(env_file=".env", protected_namespaces=[])

    @property
    def resolved_model_dir(self) -> str:
        """GLiNER model path/id with a local path expanded."""
        return _resolve(self.model_dir)

    @property
    def resolved_relation_model_dir(self) -> str:
        """GLiREL model path/id with a local path expanded."""
        return _resolve(self.relation_model_dir)
