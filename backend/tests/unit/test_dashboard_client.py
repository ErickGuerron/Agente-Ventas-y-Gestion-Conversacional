"""HTTP client the Streamlit dashboard uses to talk to the operator API (never to Telegram)."""

import json

import httpx
import pytest

from api_client import OperatorApi, OperatorApiError

KEY = "test-operator-key-0123456789"
CID = "11111111-1111-1111-1111-111111111111"


def _api(handler) -> OperatorApi:
    http = httpx.Client(
        base_url="http://api.test",
        headers={"X-Operator-Key": KEY},
        transport=httpx.MockTransport(handler),
    )
    return OperatorApi(http)


def test_list_conversations_sends_operator_key() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers["X-Operator-Key"]
        seen["path"] = request.url.path
        return httpx.Response(200, json=[{"id": CID, "status": "AI_ACTIVE"}])

    rows = _api(handler).list_conversations()

    assert seen == {"key": KEY, "path": "/api/conversations"}
    assert rows[0]["status"] == "AI_ACTIVE"


def test_takeover_and_resume_post_to_their_routes() -> None:
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append((request.method, request.url.path))
        return httpx.Response(200, json={"ok": True, "status": "HUMAN_ACTIVE", "version": 2})

    api = _api(handler)
    api.takeover(CID)
    api.resume(CID)

    assert paths == [
        ("POST", f"/api/conversations/{CID}/takeover"),
        ("POST", f"/api/conversations/{CID}/resume"),
    ]


def test_reply_sends_text_as_json() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "message_id": "m1"})

    _api(handler).reply(CID, "Hola, soy el asesor")

    assert seen["body"] == {"text": "Hola, soy el asesor"}


def test_api_error_carries_status_and_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "Take control of the conversation first"})

    with pytest.raises(OperatorApiError) as info:
        _api(handler).reply(CID, "hola")

    assert info.value.status_code == 409
    assert "Take control" in str(info.value)


def test_unreachable_api_is_an_operator_error_not_a_crash() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(OperatorApiError) as info:
        _api(handler).list_conversations()

    assert info.value.status_code == 503


def test_summary_returns_metrics() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"active_conversations": 4, "hot_leads": 1})

    assert _api(handler).summary()["hot_leads"] == 1
