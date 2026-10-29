"""Operator key authentication for dashboard REST and WebSocket, and CORS allow-list."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from main import app
from shared.database.session import get_db_session

KEY = "test-operator-key-0123456789"
PROTECTED = "/api/conversations"


class _EmptyRepo:
    def list_active_conversations(self):
        return []


class _Session:
    def commit(self):
        pass


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_KEY", KEY)
    monkeypatch.setenv("DASHBOARD_ALLOWED_ORIGINS", "http://localhost:8501")
    app.dependency_overrides[get_db_session] = lambda: _Session()
    from modules.conversations import routes

    original = routes.ConversationRepository
    routes.ConversationRepository = lambda session: _EmptyRepo()
    yield
    routes.ConversationRepository = original
    app.dependency_overrides.clear()


def test_rest_without_key_is_rejected(configured) -> None:
    res = TestClient(app).get(PROTECTED)

    assert res.status_code == 401


def test_rest_with_wrong_key_is_rejected(configured) -> None:
    res = TestClient(app).get(PROTECTED, headers={"X-Operator-Key": "nope"})

    assert res.status_code == 401


def test_rest_with_correct_key_is_allowed(configured) -> None:
    res = TestClient(app).get(PROTECTED, headers={"X-Operator-Key": KEY})

    assert res.status_code == 200


def test_rest_fails_closed_when_no_key_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_API_KEY", "")
    app.dependency_overrides[get_db_session] = lambda: _Session()
    try:
        res = TestClient(app).get(PROTECTED, headers={"X-Operator-Key": "anything"})
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 503


def test_websocket_without_token_is_refused(configured) -> None:
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/conversations/ws"):
            pass


def test_websocket_with_token_connects(configured) -> None:
    client = TestClient(app)

    with client.websocket_connect(f"/api/conversations/ws?token={KEY}") as websocket:
        websocket.send_text("ping")
        assert websocket.receive_text() == "pong"


def test_cors_allows_configured_origin_only(configured) -> None:
    client = TestClient(app)
    allowed = client.options(
        PROTECTED,
        headers={
            "Origin": "http://localhost:8501",
            "Access-Control-Request-Method": "GET",
        },
    )
    blocked = client.options(
        PROTECTED,
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )

    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:8501"
    assert "access-control-allow-origin" not in blocked.headers
