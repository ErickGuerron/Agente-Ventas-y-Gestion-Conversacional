"""Application settings loaded from environment variables (and a local .env file)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]
ENV_FILES = (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, extra="ignore")

    # Primary LLM. Used alone when CURSOR_API_KEY is empty.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"

    # Optional fallback LLM (Cursor Cloud Agents). Used only when Gemini is unavailable.
    cursor_api_key: str = ""
    cursor_model: str = ""

    # Optional MiniMax provider (OpenAI-compatible). Joins the chain after Gemini.
    minimax_api_key: str = ""
    minimax_model: str = "MiniMax-M3.1-Flash"

    telegram_webhook_secret: str = ""
    telegram_bot_token: str = ""
    database_url: str = ""

    # Operator dashboard: shared key for REST (X-Operator-Key) and WebSocket (?token=).
    # Empty means the operator API refuses every request (fail closed).
    dashboard_api_key: str = ""
    # Comma-separated origins allowed to call the API from a browser.
    dashboard_allowed_origins: str = "http://localhost:8501"

    def allowed_origins(self) -> list[str]:
        origins = self.dashboard_allowed_origins.split(",")
        return [origin.strip() for origin in origins if origin.strip()]


def get_settings() -> Settings:
    return Settings()
