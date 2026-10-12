"""Chat-model provider configuration and the agent-config payload sent to the frontend."""

from pydantic import BaseModel, Field, field_validator

from cipher.schemas._base.base import BaseModel as CamelModel, StrEnum


class LLMProvider(StrEnum):
    """Model backends the chat agent can run against."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    LOCAL = "local"


# The repo's local vLLM OpenAI-compatible server (`~/llm`, `make start` there);
# the default `LLM__BASE_URL` when `LLM__PROVIDER=local`. Shared so the chat
# backend and the analytics prompt-runner resolve `local` identically.
LOCAL_LLM_BASE_URL = "http://localhost:8002/v1"


class LLMSettings(BaseModel):
    """Server-side chat-model configuration, populated from ``LLM__*`` env vars.

    ``api_key`` falls back to the provider's own env var (``OPENAI_API_KEY``,
    ``GOOGLE_API_KEY``, ``ANTHROPIC_API_KEY``) when unset; ``local`` needs none.
    """

    provider: LLMProvider = Field(default=LLMProvider.OPENAI)
    model: str = Field(default="gpt-4o-mini")
    api_key: str | None = Field(default=None, description="Falls back to the provider's own env var if unset")
    base_url: str | None = Field(
        default=None, description="Override the provider base URL; required for a local server"
    )

    model_config = {"frozen": True}

    @field_validator("api_key", "base_url", mode="before")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        """Treat a blank ``.env`` value (``LLM__API_KEY=``) the same as an absent one.

        An empty string survives past a provider's own "is this set?" check and
        reaches the SDK client, which (Google in particular) treats an explicit
        empty ``base_url`` as an override that clobbers its computed default.
        """
        return value or None

    def openai_client_kwargs(self) -> dict[str, str]:
        """``api_key`` / ``base_url`` kwargs for an ``openai`` SDK client.

        ``local`` points at :data:`LOCAL_LLM_BASE_URL` and uses a throwaway key
        (vLLM ignores it); any other provider passes through only what is set and
        lets the SDK fall back to its own env var (``OPENAI_API_KEY``, ...).
        """
        if self.provider == LLMProvider.LOCAL:
            return {"api_key": self.api_key or "local", "base_url": self.base_url or LOCAL_LLM_BASE_URL}
        kwargs: dict[str, str] = {}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return kwargs


class ModelOption(CamelModel):
    """One selectable model in the frontend's chat model picker."""

    id: str = Field(description="`provider:model` id the chat request echoes back")
    provider: LLMProvider
    label: str
    has_key: bool = Field(description="Whether the server can authenticate this model without a client-supplied key")


class AgentConfig(CamelModel):
    """What the chat UI needs to decide whether to prompt for an API key."""

    has_server_key: bool = Field(description="Whether the server can run its default model without a client key")
    models: list[ModelOption] = Field(description="Selectable models for the picker")
    default_model_id: str = Field(description="`provider:model` the server is configured for")
