"""Builds the LLM used by the graph: Gemini first, Cursor as optional fallback."""

from modules.ai_engine.cursor_client import CursorAgentClient
from modules.ai_engine.gemini_client import GeminiClient
from modules.ai_engine.minimax_client import MinimaxClient
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
    """Chain of configured providers: Gemini, then MiniMax, then Cursor. Each one falls back to the next."""
    chain: list[LLMClient] = []
    if settings.gemini_api_key:
        chain.append(GeminiClient(api_key=settings.gemini_api_key, model=settings.gemini_model))
    if settings.minimax_api_key:
        chain.append(MinimaxClient(api_key=settings.minimax_api_key, model=settings.minimax_model))
    if settings.cursor_api_key:
        chain.append(
            CursorAgentClient(api_key=settings.cursor_api_key, model=settings.cursor_model or None)
        )
    if not chain:
        raise ValueError("Set GEMINI_API_KEY, MINIMAX_API_KEY and/or CURSOR_API_KEY")
    client = chain[-1]
    for primary in reversed(chain[:-1]):
        client = FallbackLLMClient(primary=primary, secondary=client)
    return client
