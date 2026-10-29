"""Unit tests for conversation operator endpoints and WebSocket broadcasts."""

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from main import app
from modules.channels.routes import get_telegram_service
from modules.channels.telegram_service import TelegramChannelService
from shared.database.session import get_db_session

MOCK_TOKEN = "123456789:AAE-mock-token-for-unit-testing"
OPERATOR_KEY = "test-operator-key-0123456789"
OPERATOR_HEADERS = {"X-Operator-Key": OPERATOR_KEY}


@pytest.fixture(autouse=True)
def _operator_key(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_KEY", OPERATOR_KEY)


class MockConversation:
    def __init__(
        self,
        id="conv_1",
        channel="telegram",
        external_chat_id="123456",
        status="AI_ACTIVE",
        version=1,
    ):
        self.id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        self.channel = channel
        self.external_chat_id = external_chat_id
        self.status = status
        self.version = version
        self.created_at = None


class MockMessage:
    def __init__(self, id="msg_1", sender_type="user", content="hola"):
        self.id = uuid.UUID("22222222-2222-2222-2222-222222222222")
        self.conversation_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        self.sender_type = sender_type
        self.content = content
        self.created_at = None


class MockRepo:
    def __init__(self):
        self.conv = MockConversation()
        self.messages = [MockMessage()]

    def list_active_conversations(self):
        return [self.conv]

    def get_by_id(self, cid):
        return self.conv

    def list_recent_messages(self, cid, limit=50):
        return self.messages

    def transition_status(
        self, conversation_id, expected_version, new_status, owner_id=None, event_payload=None
    ):
        if expected_version == self.conv.version:
            self.conv.status = new_status
            self.conv.version += 1
            return True
        return False

    def add_message(self, conversation_id, sender_type, content, external_message_id=None):
        msg = MockMessage(sender_type=sender_type, content=content)
        self.messages.append(msg)
        return msg


class MockSession:
    def commit(self):
        pass


def test_list_conversations():
    mock_session = MockSession()
    app.dependency_overrides[get_db_session] = lambda: mock_session

    from modules.conversations import routes

    original_repo_cls = routes.ConversationRepository
    mock_repo = MockRepo()
    routes.ConversationRepository = lambda session: mock_repo

    try:
        client = TestClient(app, headers=OPERATOR_HEADERS)
        res = client.get("/api/conversations")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["status"] == "AI_ACTIVE"
        assert data[0]["last_message"] == "hola"
    finally:
        routes.ConversationRepository = original_repo_cls
        app.dependency_overrides.clear()


def test_list_conversation_messages():
    mock_session = MockSession()
    app.dependency_overrides[get_db_session] = lambda: mock_session

    from modules.conversations import routes

    original_repo_cls = routes.ConversationRepository
    mock_repo = MockRepo()
    routes.ConversationRepository = lambda session: mock_repo

    try:
        client = TestClient(app, headers=OPERATOR_HEADERS)
        res = client.get("/api/conversations/11111111-1111-1111-1111-111111111111/messages")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["sender_type"] == "user"
        assert data[0]["content"] == "hola"
    finally:
        routes.ConversationRepository = original_repo_cls
        app.dependency_overrides.clear()


def test_operator_takeover_and_resume():
    mock_session = MockSession()
    app.dependency_overrides[get_db_session] = lambda: mock_session

    from modules.conversations import routes

    original_repo_cls = routes.ConversationRepository
    mock_repo = MockRepo()
    routes.ConversationRepository = lambda session: mock_repo

    try:
        client = TestClient(app, headers=OPERATOR_HEADERS)
        # Takeover
        res = client.post("/api/conversations/11111111-1111-1111-1111-111111111111/takeover")
        assert res.status_code == 200
        assert res.json()["status"] == "HUMAN_ACTIVE"
        assert res.json()["version"] == 2
        assert mock_repo.conv.status == "HUMAN_ACTIVE"

        # Resume
        res = client.post("/api/conversations/11111111-1111-1111-1111-111111111111/resume")
        assert res.status_code == 200
        assert res.json()["status"] == "AI_ACTIVE"
        assert res.json()["version"] == 3
        assert mock_repo.conv.status == "AI_ACTIVE"
    finally:
        routes.ConversationRepository = original_repo_cls
        app.dependency_overrides.clear()


def test_operator_reply():
    mock_session = MockSession()
    mock_tg = TelegramChannelService(token=MOCK_TOKEN)
    mock_tg.send_message = AsyncMock()

    app.dependency_overrides[get_db_session] = lambda: mock_session
    app.dependency_overrides[get_telegram_service] = lambda: mock_tg

    from modules.conversations import routes

    original_repo_cls = routes.ConversationRepository
    mock_repo = MockRepo()
    routes.ConversationRepository = lambda session: mock_repo

    try:
        mock_repo.conv.status = "HUMAN_ACTIVE"
        client = TestClient(app, headers=OPERATOR_HEADERS)
        res = client.post(
            "/api/conversations/11111111-1111-1111-1111-111111111111/reply",
            json={"text": "Hola, soy el asesor humano. ¿En qué te ayudo?"},
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True
        mock_tg.send_message.assert_awaited_once_with(
            "123456", "Hola, soy el asesor humano. ¿En qué te ayudo?"
        )
        assert mock_repo.messages[-1].sender_type == "operator"
        assert mock_repo.messages[-1].content == "Hola, soy el asesor humano. ¿En qué te ayudo?"
    finally:
        routes.ConversationRepository = original_repo_cls
        app.dependency_overrides.clear()


def test_operator_reply_rejected_while_ai_is_active():
    mock_session = MockSession()
    mock_tg = TelegramChannelService(token=MOCK_TOKEN)
    mock_tg.send_message = AsyncMock()

    app.dependency_overrides[get_db_session] = lambda: mock_session
    app.dependency_overrides[get_telegram_service] = lambda: mock_tg

    from modules.conversations import routes

    original_repo_cls = routes.ConversationRepository
    mock_repo = MockRepo()
    routes.ConversationRepository = lambda session: mock_repo

    try:
        client = TestClient(app, headers=OPERATOR_HEADERS)
        res = client.post(
            "/api/conversations/11111111-1111-1111-1111-111111111111/reply",
            json={"text": "Esto no debe salir"},
        )
        assert res.status_code == 409
        mock_tg.send_message.assert_not_awaited()
        assert all(msg.sender_type != "operator" for msg in mock_repo.messages)
    finally:
        routes.ConversationRepository = original_repo_cls
        app.dependency_overrides.clear()


def test_websocket_ping_pong():
    client = TestClient(app, headers=OPERATOR_HEADERS)
    with client.websocket_connect(f"/api/conversations/ws?token={OPERATOR_KEY}") as websocket:
        websocket.send_text("ping")
        data = websocket.receive_text()
        assert data == "pong"
