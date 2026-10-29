import os

import pytest


class FakeLLMClient:
    """Deterministic LLM for tests. Returns a canned reply and records the prompts it saw."""

    def __init__(self, reply: str = "respuesta de prueba") -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply


@pytest.fixture
def fake_llm() -> FakeLLMClient:
    return FakeLLMClient()


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set")
    return url
