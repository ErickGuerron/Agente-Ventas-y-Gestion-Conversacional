"""Factory for default LLM client and sales graph based on configuration."""

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from modules.ai_engine.gemini_client import GeminiClient
from modules.ai_engine.graph import build_graph
from modules.ai_engine.ports import LLMClient
from modules.courses.catalog import load_catalog
from shared.config.settings import get_settings

_GLOBAL_CHECKPOINTER = InMemorySaver()


class EchoFallbackLLMClient:
    """Fallback LLM used when provider is fake or api key is missing."""

    def __init__(self, reply: str | None = None) -> None:
        self.reply = reply

    def generate(self, prompt: str) -> str:
        if self.reply:
            return self.reply
        if "Devuelve EXCLUSIVAMENTE un objeto JSON" in prompt:
            return '{"intent": "academic", "lead_status": "INTERESADO"}'
        return (
            "¡Hola! Soy el asistente virtual del centro de transferencia tecnológica CTT-FISEI. "
            "Contamos con cursos en Fundamentos de Python 1 y 2, CCNA Redes e Inteligencia "
            "Artificial. ¿Qué área te gustaría conocer?"
        )


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider == "gemini" and settings.gemini_api_key:
        return GeminiClient(api_key=settings.gemini_api_key, model="gemini-1.5-flash")
    return EchoFallbackLLMClient()


def get_sales_graph(
    llm: LLMClient | None = None,
    checkpointer: Any | None = None,
) -> Any:
    """Create or compile the sales graph with shared in-memory checkpointer."""
    client = llm or get_llm_client()
    return build_graph(
        llm=client,
        catalog=load_catalog(),
        checkpointer=checkpointer or _GLOBAL_CHECKPOINTER,
    )
