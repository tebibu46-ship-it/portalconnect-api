"""Application configuration loaded from environment and optional .env files."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the PortalConnect services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    test_mode: bool = False
    api_key: str | None = None
    rate_limit_per_minute: int = 120
    rate_limit_enabled: bool = True
    sms_webhook_url: str | None = None
    ais_feed_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""

    return Settings()
