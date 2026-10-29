"""Application settings loaded from environment variables (and a local .env file)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]
ENV_FILES = (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, extra="ignore")

    llm_provider: str = "fake"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    telegram_webhook_secret: str = ""
    telegram_bot_token: str = ""
    database_url: str = ""


def get_settings() -> Settings:
    return Settings()
