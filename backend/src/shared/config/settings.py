"""Application settings loaded from environment variables (and .env locally)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "fake"
    gemini_api_key: str = ""
    telegram_webhook_secret: str = ""
    telegram_bot_token: str = ""
    database_url: str = ""


def get_settings() -> Settings:
    return Settings()
