from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogLevel(StrEnum):
    """Log level enumeration."""

    debug = "DEBUG"
    info = "INFO"
    warning = "WARNING"
    error = "ERROR"
    critical = "CRITICAL"


class LogConfig(BaseModel):
    """Log configuration model."""

    file: Path | None = Field(None, description="File to write logs to if desired")
    level: LogLevel = Field(LogLevel.info, description="Log level")
    to_json: bool = Field(False, description="Log in JSON format")

    @field_validator("level", mode="before")
    @classmethod
    def uppercase_level(cls, value: LogLevel) -> LogLevel:
        """Ensure log level is uppercase."""
        return value.upper()


class BaseServiceSettings(BaseSettings):
    """Cipher service settings model."""

    host: str = Field("0.0.0.0", description="The host to run the cipher on")
    port: int = Field(8000, description="The port to run the cipher on")
    reload: bool = Field(True, description="Reload the server on changes")
    log: LogConfig = Field(LogConfig(), description="Log configuration object")
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="allow")
