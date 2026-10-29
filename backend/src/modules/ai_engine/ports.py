"""Port for the LLM. The graph depends on this protocol, never on a vendor SDK directly."""

from typing import Protocol


class LLMUnavailableError(RuntimeError):
    """The provider cannot answer right now (quota exhausted, rate limited, overloaded).

    Only this error triggers the fallback provider. Configuration or request errors
    (bad key, invalid request) must surface instead of silently switching providers.
    """


class LLMClient(Protocol):
    def generate(self, prompt: str) -> str: ...
