"""pyprompt service settings.

The LLM connection reuses the same ``LLM__*`` env contract as the chat backend
(`cipher.schemas.interaction.llm.LLMSettings`): point ``LLM__BASE_URL`` at
OpenAI, a local vLLM server, or any OpenAI-compatible endpoint. Only the
`openai` SDK is used, so a non-OpenAI provider must speak that wire format.
"""

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from cipher.schemas.interaction.llm import LLMSettings
from cipher.utils.fastapi.settings import BaseServiceSettings


class Settings(BaseServiceSettings):
    """pyprompt service settings."""

    llm: LLMSettings = Field(
        default_factory=LLMSettings,
        description="Model + credentials, from LLM__PROVIDER / LLM__MODEL / LLM__API_KEY / LLM__BASE_URL",
    )
    temperature: float = Field(
        default=0.0, ge=0, le=2, description="Sampling temperature for extraction calls", alias="PROMPT_TEMPERATURE"
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Re-asks on a schema-validation failure, feeding the error back",
        alias="PROMPT_MAX_RETRIES",
    )
    request_timeout: float = Field(
        default=90.0, gt=0, description="Per-request timeout in seconds", alias="PROMPT_REQUEST_TIMEOUT"
    )
    max_input_chars: int = Field(
        default=48_000,
        gt=0,
        description="Source text is truncated to this many characters before the prompt is built",
        alias="PROMPT_MAX_INPUT_CHARS",
    )

    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", protected_namespaces=[])
