"""Build a pydantic_ai model from `LLMSettings`, and enumerate the picker's options."""

from pydantic_ai.models import Model

from cipher.schemas.interaction.llm import LOCAL_LLM_BASE_URL, LLMProvider, LLMSettings, ModelOption

# `LOCAL_LLM_BASE_URL` (the vLLM OpenAI-compatible server in ~/llm, `make start`
# there) is shared from cipher-schemas so chat and the analytics prompt-runner
# resolve `LLM__PROVIDER=local` to the same endpoint. vLLM ignores the key.
__all__ = ["LOCAL_LLM_BASE_URL", "AVAILABLE_MODELS", "resolve_llm_settings", "build_model", "can_build"]

# The model picker shown in the chat UI. `has_key` here is a placeholder --
# the /chat/config route recomputes it per model against the server's settings.
AVAILABLE_MODELS: tuple[ModelOption, ...] = (
    ModelOption(id="openai:gpt-4o-mini", provider=LLMProvider.OPENAI, label="GPT-4o Mini", has_key=False),
    ModelOption(id="openai:gpt-4o", provider=LLMProvider.OPENAI, label="GPT-4o", has_key=False),
    ModelOption(
        id="anthropic:claude-haiku-4-5-20251001",
        provider=LLMProvider.ANTHROPIC,
        label="Claude Haiku",
        has_key=False,
    ),
    ModelOption(id="anthropic:claude-sonnet-4-5", provider=LLMProvider.ANTHROPIC, label="Claude Sonnet", has_key=False),
    ModelOption(id="google:gemini-2.5-flash", provider=LLMProvider.GOOGLE, label="Gemini 2.5 Flash", has_key=False),
    ModelOption(
        id="google:gemini-2.5-flash-lite",
        provider=LLMProvider.GOOGLE,
        label="Gemini 2.5 Flash Lite",
        has_key=False,
    ),
    ModelOption(id="google:gemini-2.5-pro", provider=LLMProvider.GOOGLE, label="Gemini 2.5 Pro", has_key=False),
    ModelOption(id="local:gemma-3n-E2B-it", provider=LLMProvider.LOCAL, label="Gemma 3n E2B (local)", has_key=True),
)


def resolve_llm_settings(base: LLMSettings, model_id: str | None) -> LLMSettings:
    """Apply a `provider:model` picker id on top of the server's base settings.

    The server's single `LLM__API_KEY` is only valid for `base.provider`, so
    switching to a different provider drops it and lets that provider's own env
    var (`OPENAI_API_KEY`, ...) take over. An unknown or malformed id is ignored.
    """
    if not model_id:
        return base
    provider_str, _, model_name = model_id.partition(":")
    if not model_name:
        return base
    try:
        provider = LLMProvider(provider_str)
    except ValueError:
        return base
    update: dict[str, object] = {"provider": provider, "model": model_name}
    if provider == LLMProvider.LOCAL:
        update["api_key"] = "local"
        update["base_url"] = base.base_url or LOCAL_LLM_BASE_URL
    elif provider != base.provider:
        update["api_key"] = None
    return base.model_copy(update=update)


def build_model(settings: LLMSettings) -> Model:
    """Construct the pydantic_ai model for `agent.run` / `adapter.run_stream`.

    Raises if the resolved provider has no key to authenticate with (neither in
    `settings` nor the provider's env var); `can_build` wraps that for probing.
    """
    if settings.provider in (LLMProvider.OPENAI, LLMProvider.LOCAL):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        if settings.provider == LLMProvider.LOCAL:
            provider = OpenAIProvider(base_url=settings.base_url or LOCAL_LLM_BASE_URL, api_key="local")
        elif settings.base_url:
            provider = OpenAIProvider(api_key=settings.api_key, base_url=settings.base_url)
        else:
            provider = OpenAIProvider(api_key=settings.api_key)
        return OpenAIChatModel(settings.model, provider=provider)
    if settings.provider == LLMProvider.ANTHROPIC:
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        if settings.base_url:
            provider = AnthropicProvider(api_key=settings.api_key, base_url=settings.base_url)
        else:
            provider = AnthropicProvider(api_key=settings.api_key)
        return AnthropicModel(settings.model, provider=provider)
    if settings.provider == LLMProvider.GOOGLE:
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        return GoogleModel(settings.model, provider=GoogleProvider(api_key=settings.api_key))
    raise ValueError(f"Unsupported LLM provider: {settings.provider}")


def can_build(settings: LLMSettings) -> bool:
    """Whether `build_model` succeeds -- i.e. the provider has a usable key. No network call."""
    try:
        build_model(settings)
    except Exception:
        return False
    return True
