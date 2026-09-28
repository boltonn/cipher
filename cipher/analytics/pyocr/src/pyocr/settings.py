from pydantic import Field
from pydantic_settings import SettingsConfigDict

from cipher.utils.fastapi.settings import BaseServiceSettings
from pyocr.engine import EngineConfig
from pyocr.pages import DEFAULT_MAX_SIDE


class Settings(BaseServiceSettings):
    """pyocr service settings; engine knobs come from `OCR__*` (e.g. OCR__BACKEND=transformers)."""

    ocr: EngineConfig = Field(default_factory=EngineConfig)
    max_side: int = Field(
        default=DEFAULT_MAX_SIDE, description="Longest side pages are rendered at", alias="OCR_MAX_SIDE"
    )
    reload: bool = Field(default=False, description="Reloading would re-load the model on every edit")

    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="allow")
