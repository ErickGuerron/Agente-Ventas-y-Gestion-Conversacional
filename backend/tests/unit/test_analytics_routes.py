"""Operator-only metrics endpoint for the dashboard."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from main import app
from shared.database.session import get_db_session

KEY = "test-operator-key-0123456789"


class _FakeRepo:
    def list_active_conversations(self):
        return [SimpleNamespace(status="AI_ACTIVE"), SimpleNamespace(status="HUMAN_ACTIVE")]

    def latest_leads_by_conversation(self):
        return {"a": "LEAD_CALIENTE"}

    def analysis_points(self):
        return [("ACADEMICO", 200, 50)]

    def message_times_since(self, since):
        return []

    def failed_jobs_count(self):
        return 2


class _Session:
    def commit(self):
        pass


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("DASHBOARD_API_KEY", KEY)
    app.dependency_overrides[get_db_session] = lambda: _Session()
    from modules.analytics import routes

    routes.ConversationRepository = lambda session: _FakeRepo()
    return TestClient(app, headers={"X-Operator-Key": KEY})


def test_summary_requires_operator_key(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_API_KEY", KEY)
    app.dependency_overrides[get_db_session] = lambda: _Session()
    try:
        res = TestClient(app).get("/api/analytics/summary")
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 401


def test_summary_returns_dashboard_metrics(monkeypatch) -> None:
    client = _client(monkeypatch)
    try:
        res = client.get("/api/analytics/summary")
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    body = res.json()
    assert body["active_conversations"] == 2
    assert body["human_escalations"] == 1
    assert body["hot_leads"] == 1
    assert body["intent_distribution"] == {"ACADEMICO": 1}
    assert body["avg_response_ms"] == 200
    assert body["total_tokens"] == 50
    assert body["failed_jobs"] == 2
    assert len(body["messages_per_hour"]) == 24
