from types import SimpleNamespace

import pytest

from modules.ai_engine.gemini_client import GeminiClient


class _FakeModels:
    def __init__(self, text: str | None) -> None:
        self.text = text
        self.calls: list[dict[str, str]] = []

    def generate_content(self, model: str, contents: str) -> SimpleNamespace:
        self.calls.append({"model": model, "contents": contents})
        return SimpleNamespace(text=self.text)


def _sdk(text: str | None) -> SimpleNamespace:
    return SimpleNamespace(models=_FakeModels(text))


def test_generate_sends_prompt_to_configured_model_and_returns_text() -> None:
    sdk = _sdk("Hola, soy el asistente")
    client = GeminiClient(api_key="unused", model="gemini-2.5-flash", client=sdk)

    reply = client.generate("¿Qué cursos hay?")

    assert reply == "Hola, soy el asistente"
    assert sdk.models.calls == [{"model": "gemini-2.5-flash", "contents": "¿Qué cursos hay?"}]


def test_generate_rejects_empty_response() -> None:
    client = GeminiClient(api_key="unused", model="m", client=_sdk(None))

    with pytest.raises(RuntimeError, match="empty response"):
        client.generate("hola")


def test_missing_api_key_fails_fast_without_injected_client() -> None:
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiClient(api_key="", model="m")
