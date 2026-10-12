"""pyvllm settings, read from the environment and `.env`."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Auth shared by the served models and their clients."""

    api_key: str | None = Field(
        default=None, alias="VLLM_API_KEY", description="Bearer key every served model requires (none: open)"
    )
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    @property
    def auth_headers(self) -> dict[str, str]:
        """`Authorization` header for a request to a served model, empty when no key is set."""
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}


settings = Settings()
