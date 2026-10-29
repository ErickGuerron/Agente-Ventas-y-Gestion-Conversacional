"""Builds the LLM used by the graph: Gemini first, Cursor as optional fallback."""

from modules.ai_engine.cursor_client import CursorAgentClient
from modules.ai_engine.gemini_client import GeminiClient
from modules.ai_engine.ports import LLMClient, LLMUnavailableError
from shared.config.settings import Settings


class FallbackLLMClient:
    """Uses ``primary`` and switches to ``secondary`` only when the primary is unavailable."""

    def __init__(self, primary: LLMClient, secondary: LLMClient) -> None:
        self._primary = primary
        self._secondary = secondary

    def generate(self, prompt: str) -> str:
        try:
            return self._primary.generate(prompt)
        except LLMUnavailableError:
            return self._secondary.generate(prompt)


def build_llm_client(settings: Settings) -> LLMClient:
    gemini = (
        GeminiClient(api_key=settings.gemini_api_key, model=settings.gemini_model)
        if settings.gemini_api_key
        else None
    )
    cursor = (
        CursorAgentClient(api_key=settings.cursor_api_key, model=settings.cursor_model or None)
        if settings.cursor_api_key
        else None
    )
    if gemini is not None and cursor is not None:
        return FallbackLLMClient(primary=gemini, secondary=cursor)
    if gemini is not None:
        return gemini
    if cursor is not None:
        return cursor
    raise ValueError("Set GEMINI_API_KEY and/or CURSOR_API_KEY")
