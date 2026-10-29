"""Port for the LLM. The graph depends on this protocol, never on the Gemini SDK directly."""

from typing import Protocol


class LLMClient(Protocol):
    def generate(self, prompt: str) -> str: ...
