"""Unit tests for Telegram webhook endpoint and parsing."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from main import app
from modules.ai_engine.factory import get_llm_client
from modules.channels.dto import IncomingMessage
from modules.channels.telegram_service import TelegramChannelService
from shared.config.settings import Settings, get_settings

MOCK_TOKEN = "123456789:AAE-mock-token-for-unit-testing"


def test_parse_update_extracts_incoming_message():
    service = TelegramChannelService(token=MOCK_TOKEN)
    payload = {
        "update_id": 1001,
        "message": {
            "message_id": 42,
            "from": {"first_name": "Carlos", "last_name": "Mera", "username": "carlos_m"},
            "chat": {"id": 987654321},
            "text": "¿Tienen cursos de ciberseguridad?",
        },
    }

    incoming = service.parse_update(payload)
    assert incoming is not None
    assert incoming.channel == "telegram"
    assert incoming.external_chat_id == "987654321"
    assert incoming.external_message_id == "42"
    assert incoming.text == "¿Tienen cursos de ciberseguridad?"
    assert incoming.sender_name == "Carlos Mera"
    assert incoming.username == "carlos_m"


def test_parse_update_ignores_non_text_updates():
    service = TelegramChannelService(token=MOCK_TOKEN)
    payload = {
        "update_id": 1002,
        "message": {
            "message_id": 43,
            "chat": {"id": 12345},
            "photo": [{"file_id": "xyz"}],
        },
    }

    assert service.parse_update(payload) is None


def test_webhook_rejects_invalid_secret(fake_llm):
    settings = Settings(telegram_webhook_secret="secret_123")
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_llm_client] = lambda: fake_llm

    client = TestClient(app)
    response = client.post(
        "/api/telegram/webhook",
        json={"message": {"text": "hola", "chat": {"id": 1}}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"},
    )
    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_webhook_skips_empty_update(fake_llm):
    settings = Settings(telegram_webhook_secret="")
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_llm_client] = lambda: fake_llm

    client = TestClient(app)
    response = client.post(
        "/api/telegram/webhook",
        json={"some_random_event": True},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "skipped": True}
    app.dependency_overrides.clear()


def test_process_incoming_message_ai_active_dispatches_reply(fake_llm):
    mock_service = TelegramChannelService(token=MOCK_TOKEN)
    mock_service.send_message = AsyncMock()

    class MockRepo:
        def __init__(self):
            self.messages = []

        def get_or_create(self, channel, external_chat_id):
            class MockConv:
                id = "conv_1"
                status = "AI_ACTIVE"

            return MockConv()

        def add_message(self, conversation_id, sender_type, content, external_message_id=None):
            self.messages.append((sender_type, content))

    repo = MockRepo()
    incoming = IncomingMessage(
        channel="telegram",
        external_chat_id="12345",
        external_message_id="99",
        text="¿Cuánto cuesta Python?",
    )

    import asyncio

    reply = asyncio.run(mock_service.process_incoming_message(incoming, repo, fake_llm))

    assert reply == fake_llm.reply
    assert ("user", "¿Cuánto cuesta Python?") in repo.messages
    assert ("ai", fake_llm.reply) in repo.messages
    mock_service.send_message.assert_awaited_once_with("12345", fake_llm.reply)
