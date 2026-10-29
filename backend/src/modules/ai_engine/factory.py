"""Factory for default LLM client based on configuration."""

from modules.ai_engine.gemini_client import GeminiClient
from modules.ai_engine.ports import LLMClient
from shared.config.settings import get_settings


class EchoFallbackLLMClient:
    """Fallback LLM used when provider is fake or api key is missing."""

    def __init__(self, reply: str | None = None) -> None:
        self.reply = reply

    def generate(self, prompt: str) -> str:
        if self.reply:
            return self.reply
        return (
            "¡Hola! Soy el asistente virtual del centro de capacitación de la UTA. "
            "Contamos con cursos en Python IA, Cloud DevOps y Ciberseguridad. "
            "¿Qué área te gustaría conocer?"
        )


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider == "gemini" and settings.gemini_api_key:
        return GeminiClient(api_key=settings.gemini_api_key, model="gemini-1.5-flash")
    return EchoFallbackLLMClient()
