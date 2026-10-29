import json

import httpx
import pytest

from modules.ai_engine.llm_factory import FallbackLLMClient, build_llm_client
from modules.ai_engine.minimax_client import MinimaxClient
from modules.ai_engine.ports import LLMUnavailableError
from shared.config.settings import Settings


def _minimax(handler, model: str = "MiniMax-M3.1-Flash") -> MinimaxClient:
    http = httpx.Client(
        base_url="https://api.minimax.io",
        headers={"Authorization": "Bearer unused"},
        transport=httpx.MockTransport(handler),
    )
    return MinimaxClient(api_key="unused", model=model, client=http)


def _ok(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_minimax_returns_message_content_and_sends_chat_request() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return _ok("Hola desde MiniMax")

    client = _minimax(handler)

    assert client.generate("¿Qué cursos hay?") == "Hola desde MiniMax"
    assert seen["path"] == "/v1/chat/completions"
    assert seen["auth"] == "Bearer unused"
    assert seen["body"]["model"] == "MiniMax-M3.1-Flash"
    assert seen["body"]["messages"] == [{"role": "user", "content": "¿Qué cursos hay?"}]
    assert seen["body"]["reasoning_effort"] == "low"
    assert seen["body"]["reasoning_split"] is True


@pytest.mark.parametrize("code", [429, 503])
def test_minimax_rate_limit_and_overload_become_unavailable(code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, json={"error": "busy"})

    with pytest.raises(LLMUnavailableError):
        _minimax(handler).generate("hola")


def test_minimax_bad_key_is_not_treated_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid key"})

    with pytest.raises(RuntimeError, match="401") as info:
        _minimax(handler).generate("hola")
    assert not isinstance(info.value, LLMUnavailableError)


def test_minimax_network_failure_becomes_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(LLMUnavailableError):
        _minimax(handler).generate("hola")


def test_minimax_empty_content_is_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok("   ")

    with pytest.raises(RuntimeError, match="empty"):
        _minimax(handler).generate("hola")


def test_factory_with_only_minimax_key_uses_minimax() -> None:
    settings = Settings(
        gemini_api_key="", cursor_api_key="", minimax_api_key="mm-key", _env_file=None
    )

    assert isinstance(build_llm_client(settings), MinimaxClient)


def test_factory_with_gemini_and_minimax_builds_fallback_chain() -> None:
    settings = Settings(
        gemini_api_key="gem-key", cursor_api_key="", minimax_api_key="mm-key", _env_file=None
    )

    assert isinstance(build_llm_client(settings), FallbackLLMClient)
