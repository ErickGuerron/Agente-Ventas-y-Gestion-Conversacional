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


def test_process_incoming_message_frustration_triggers_handover_transition():
    import asyncio

    from modules.ai_engine.graph import HUMAN_HANDOFF_TEXT

    mock_service = TelegramChannelService(token=MOCK_TOKEN)
    mock_service.send_message = AsyncMock()

    class ScriptedLLM:
        def __init__(self, *replies: str):
            self._replies = list(replies)

        def generate(self, prompt: str) -> str:
            return self._replies.pop(0)

    # First generate call is analysis_prompt -> returns FRUSTRADO
    frustrated_llm = ScriptedLLM('{"intent": "sales", "lead_status": "FRUSTRADO"}')

    class MockRepo:
        def __init__(self):
            self.messages = []
            self.transition_calls = []
            self.analysis_calls = []

        def get_or_create(self, channel, external_chat_id):
            class MockConv:
                id = "conv_1"
                status = "AI_ACTIVE"
                version = 1

            return MockConv()

        def add_message(self, conversation_id, sender_type, content, external_message_id=None):
            class MockMsg:
                id = "msg_100"

            self.messages.append((sender_type, content))
            return MockMsg()

        def transition_status(
            self, conversation_id, expected_version, new_status, owner_id=None, event_payload=None
        ):
            self.transition_calls.append(
                (conversation_id, expected_version, new_status, event_payload)
            )
            return True

        def save_analysis(self, message_id, intent, lead_status, latency_ms=0, token_usage=0):
            self.analysis_calls.append((message_id, intent, lead_status, latency_ms))

    repo = MockRepo()
    incoming = IncomingMessage(
        channel="telegram",
        external_chat_id="999",
        text="Esto es un pésimo servicio, quiero hablar con alguien ya!",
    )

    reply = asyncio.run(mock_service.process_incoming_message(incoming, repo, llm=frustrated_llm))

    assert reply == HUMAN_HANDOFF_TEXT
    assert len(repo.transition_calls) == 1
    cid, expected_ver, new_status, payload = repo.transition_calls[0]
    assert cid == "conv_1"
    assert expected_ver == 1
    assert new_status == "HUMAN_ACTIVE"
    assert payload["reason"] == "frustration_or_human_handoff"

    assert len(repo.analysis_calls) == 1
    assert repo.analysis_calls[0][1] == "sales"
    assert repo.analysis_calls[0][2] == "FRUSTRADO"

    mock_service.send_message.assert_awaited_once_with("999", HUMAN_HANDOFF_TEXT)


def test_process_incoming_message_silence_after_handover():
    import asyncio

    mock_service = TelegramChannelService(token=MOCK_TOKEN)
    mock_service.send_message = AsyncMock()

    class MockRepo:
        def __init__(self):
            self.messages = []

        def get_or_create(self, channel, external_chat_id):
            class MockConv:
                id = "conv_1"
                status = "HUMAN_ACTIVE"  # Handover active!
                version = 2

            return MockConv()

        def add_message(self, conversation_id, sender_type, content, external_message_id=None):
            self.messages.append((sender_type, content))

    repo = MockRepo()
    incoming = IncomingMessage(
        channel="telegram",
        external_chat_id="999",
        text="¿Hay alguien ahí?",
    )

    reply = asyncio.run(mock_service.process_incoming_message(incoming, repo))

    assert reply is None
    assert ("user", "¿Hay alguien ahí?") in repo.messages
    mock_service.send_message.assert_not_awaited()


def test_process_incoming_message_discards_reply_if_operator_took_control_concurrency():
    import asyncio

    mock_service = TelegramChannelService(token=MOCK_TOKEN)
    mock_service.send_message = AsyncMock()

    class ScriptedLLM:
        def generate(self, prompt: str) -> str:
            if "JSON" in prompt:
                return '{"intent": "academic", "lead_status": "INTERESADO"}'
            return "Respuesta académica normal"

    llm = ScriptedLLM()

    class MockRepo:
        def __init__(self):
            self.messages = []

        def get_or_create(self, channel, external_chat_id):
            class InitialConv:
                id = "conv_1"
                status = "AI_ACTIVE"
                version = 1

            return InitialConv()

        def get_by_id(self, conversation_id):
            # Operator took over during inference!
            class TakenOverConv:
                id = "conv_1"
                status = "HUMAN_ACTIVE"
                version = 2

            return TakenOverConv()

        def add_message(self, conversation_id, sender_type, content, external_message_id=None):
            self.messages.append((sender_type, content))

    repo = MockRepo()
    incoming = IncomingMessage(
        channel="telegram",
        external_chat_id="888",
        text="¿Qué cursos tienen?",
    )

    reply = asyncio.run(mock_service.process_incoming_message(incoming, repo, llm=llm))

    assert reply is None
    mock_service.send_message.assert_not_awaited()
