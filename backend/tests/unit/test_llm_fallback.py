from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors as genai_errors

from modules.ai_engine.cursor_client import CursorAgentClient
from modules.ai_engine.gemini_client import GeminiClient
from modules.ai_engine.llm_factory import FallbackLLMClient, build_llm_client
from modules.ai_engine.ports import LLMUnavailableError
from shared.config.settings import Settings


class _Raising:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def generate(self, prompt: str) -> str:
        raise self._error


class _Answering:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        return self.reply


def _GeminiSDKRaising(code: int) -> SimpleNamespace:
    """Stands in for the google-genai client and raises a configured APIError on every call."""
    error = genai_errors.APIError(code, {"error": {"message": "boom"}})

    def generate_content(model: str, contents: str):
        raise error

    return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))


def test_fallback_uses_secondary_only_when_primary_is_unavailable() -> None:
    secondary = _Answering("respuesta de respaldo")
    client = FallbackLLMClient(
        primary=_Raising(LLMUnavailableError("cuota agotada")), secondary=secondary
    )

    assert client.generate("hola") == "respuesta de respaldo"
    assert secondary.calls == 1


def test_fallback_does_not_hide_configuration_errors() -> None:
    secondary = _Answering("no debería usarse")
    client = FallbackLLMClient(
        primary=_Raising(RuntimeError("API key inválida")), secondary=secondary
    )

    with pytest.raises(RuntimeError, match="API key inválida"):
        client.generate("hola")
    assert secondary.calls == 0


def test_primary_answer_skips_secondary() -> None:
    secondary = _Answering("respaldo")
    client = FallbackLLMClient(primary=_Answering("principal"), secondary=secondary)

    assert client.generate("hola") == "principal"
    assert secondary.calls == 0


@pytest.mark.parametrize("code", [429, 503])
def test_gemini_quota_and_overload_become_unavailable(code: int) -> None:
    client = GeminiClient(api_key="unused", model="m", client=_GeminiSDKRaising(code))

    with pytest.raises(LLMUnavailableError):
        client.generate("hola")


def test_gemini_bad_request_is_not_treated_as_unavailable() -> None:
    client = GeminiClient(api_key="unused", model="m", client=_GeminiSDKRaising(400))

    with pytest.raises(genai_errors.APIError):
        client.generate("hola")


def _cursor_transport(run_statuses: list[str], result: str = "respuesta cursor"):
    """Fake Cloud Agents API: create -> poll runs with the given statuses -> delete."""
    state = {"polls": 0, "deleted": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/agents":
            return httpx.Response(
                200,
                json={
                    "agent": {"id": "bc-1", "latestRunId": "run-1"},
                    "run": {"id": "run-1", "status": "CREATING"},
                },
            )
        if request.method == "GET" and request.url.path == "/v1/agents/bc-1/runs/run-1":
            status = run_statuses[min(state["polls"], len(run_statuses) - 1)]
            state["polls"] += 1
            body = {"id": "run-1", "status": status}
            if status == "FINISHED":
                body["result"] = result
            return httpx.Response(200, json=body)
        if request.method == "DELETE" and request.url.path == "/v1/agents/bc-1":
            state["deleted"] = True
            return httpx.Response(200, json={"id": "bc-1"})
        return httpx.Response(404, json={"error": "Not Found"})

    return handler, state


def _cursor(handler, timeout: float = 60.0) -> CursorAgentClient:
    http = httpx.Client(base_url="https://api.cursor.com", transport=httpx.MockTransport(handler))
    return CursorAgentClient(
        api_key="unused", client=http, poll_interval=0, timeout=timeout, sleep=lambda _: None
    )


def test_cursor_agent_returns_result_and_deletes_agent() -> None:
    handler, state = _cursor_transport(["RUNNING", "FINISHED"], result="Hola desde Cursor")
    client = _cursor(handler)

    assert client.generate("¿Qué cursos hay?") == "Hola desde Cursor"
    assert state["deleted"] is True


def test_cursor_failed_run_raises_and_still_deletes_agent() -> None:
    handler, state = _cursor_transport(["ERROR"])
    client = _cursor(handler)

    with pytest.raises(RuntimeError, match="ERROR"):
        client.generate("hola")
    assert state["deleted"] is True


def test_cursor_rate_limit_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "Too Many Requests"})

    with pytest.raises(LLMUnavailableError):
        _cursor(handler).generate("hola")


def test_cursor_run_that_never_finishes_times_out_as_unavailable() -> None:
    handler, _ = _cursor_transport(["RUNNING"])
    client = _cursor(handler, timeout=0)

    with pytest.raises(LLMUnavailableError, match="timed out"):
        client.generate("hola")


def test_factory_without_cursor_key_uses_only_gemini() -> None:
    settings = Settings(
        gemini_api_key="gem-key", cursor_api_key="", minimax_api_key="", _env_file=None
    )

    assert isinstance(build_llm_client(settings), GeminiClient)


def test_factory_with_both_keys_builds_fallback_chain() -> None:
    settings = Settings(gemini_api_key="gem-key", cursor_api_key="cur-key", _env_file=None)

    assert isinstance(build_llm_client(settings), FallbackLLMClient)


def test_factory_without_any_key_fails_fast() -> None:
    settings = Settings(gemini_api_key="", cursor_api_key="", minimax_api_key="", _env_file=None)

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        build_llm_client(settings)
