"""Integration test for Telegram webhook connected to live Supabase database."""

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from modules.ai_engine.factory import get_llm_client
from modules.channels.routes import get_telegram_service
from modules.channels.telegram_service import TelegramChannelService
from modules.conversations.repository import ConversationRepository
from shared.config.settings import Settings, get_settings
from shared.database.base import Base
from shared.database.engine import make_engine
from shared.database.session import get_db_session

MOCK_SECRET = "test_webhook_secret_123"
MOCK_TOKEN = "123456789:AAE-mock-token-for-unit-testing"


@pytest.fixture
def db_session(database_url: str):
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
        session.rollback()


@pytest.mark.integration
def test_telegram_webhook_end_to_end_supabase_flow(db_session: Session, fake_llm):
    test_chat_id = f"tg_{uuid.uuid4().hex[:10]}"

    # Mock Telegram dispatch to avoid external network call
    mock_service = TelegramChannelService(token=MOCK_TOKEN)
    mock_service.send_message = AsyncMock()

    settings = Settings(telegram_webhook_secret=MOCK_SECRET, telegram_bot_token=MOCK_TOKEN)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_telegram_service] = lambda: mock_service
    app.dependency_overrides[get_llm_client] = lambda: fake_llm

    client = TestClient(app)

    payload = {
        "update_id": 99999,
        "message": {
            "message_id": 101,
            "from": {"first_name": "Estudiante", "last_name": "Prueba", "username": "estudiante_p"},
            "chat": {"id": int(test_chat_id[3:], 16) % 100000000},
            "text": "Hola, ¿tienen becas disponibles para Cloud?",
        },
    }

    numeric_chat_id = str(payload["message"]["chat"]["id"])

    response = client.post(
        "/api/telegram/webhook",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": MOCK_SECRET},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "reply_generated": True}

    # Verify rows in Supabase
    repo = ConversationRepository(db_session)
    conv = repo.get_or_create("telegram", numeric_chat_id)
    assert conv is not None
    assert conv.status == "AI_ACTIVE"

    messages = repo.list_recent_messages(conv.id)
    assert len(messages) >= 2
    assert messages[0].sender_type == "user"
    assert "Hola, ¿tienen becas disponibles para Cloud?" in messages[0].content
    assert messages[1].sender_type == "ai"
    assert messages[1].content == fake_llm.reply

    # Clean up test rows
    db_session.delete(conv)
    db_session.commit()
    app.dependency_overrides.clear()


@pytest.mark.integration
def test_telegram_webhook_frustration_handover_supabase_flow(db_session: Session):
    test_chat_id = f"tg_{uuid.uuid4().hex[:10]}"
    numeric_chat_id = str(int(test_chat_id[3:], 16) % 100000000)

    class FrustratedLLM:
        def generate(self, prompt: str) -> str:
            if "JSON" in prompt:
                return '{"intent": "sales", "lead_status": "FRUSTRADO"}'
            return "Respuesta no debería usarse"

    mock_service = TelegramChannelService(token=MOCK_TOKEN)
    mock_service.send_message = AsyncMock()

    settings = Settings(telegram_webhook_secret=MOCK_SECRET, telegram_bot_token=MOCK_TOKEN)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_telegram_service] = lambda: mock_service
    app.dependency_overrides[get_llm_client] = lambda: FrustratedLLM()

    client = TestClient(app)

    # 1. First message: Frustrated user
    payload1 = {
        "update_id": 10001,
        "message": {
            "message_id": 201,
            "from": {"first_name": "Usuario", "last_name": "Molesto", "username": "u_molesto"},
            "chat": {"id": int(numeric_chat_id)},
            "text": "¡Nadie me ayuda, pésima atención!",
        },
    }

    resp1 = client.post(
        "/api/telegram/webhook",
        json=payload1,
        headers={"X-Telegram-Bot-Api-Secret-Token": MOCK_SECRET},
    )
    assert resp1.status_code == 200
    assert resp1.json() == {"ok": True, "reply_generated": True}

    # Verify handover in Supabase
    repo = ConversationRepository(db_session)
    conv = repo.get_or_create("telegram", numeric_chat_id)
    assert conv.status == "HUMAN_ACTIVE"
    assert conv.version >= 2

    # Verify handover message sent
    messages = repo.list_recent_messages(conv.id)
    assert len(messages) >= 2
    assert messages[-1].sender_type == "ai"
    assert "asesor" in messages[-1].content.lower()

    # 2. Second message: User writes again while HUMAN_ACTIVE -> Bot must keep silence
    payload2 = {
        "update_id": 10002,
        "message": {
            "message_id": 202,
            "from": {"first_name": "Usuario", "last_name": "Molesto", "username": "u_molesto"},
            "chat": {"id": int(numeric_chat_id)},
            "text": "Sigo esperando...",
        },
    }

    resp2 = client.post(
        "/api/telegram/webhook",
        json=payload2,
        headers={"X-Telegram-Bot-Api-Secret-Token": MOCK_SECRET},
    )
    assert resp2.status_code == 200
    assert resp2.json() == {"ok": True, "reply_generated": False}

    # Message persisted, but no new AI reply
    messages_after = repo.list_recent_messages(conv.id)
    assert len(messages_after) == 3
    assert messages_after[-1].sender_type == "user"
    assert messages_after[-1].content == "Sigo esperando..."

    # Clean up test rows
    db_session.delete(conv)
    db_session.commit()
    app.dependency_overrides.clear()
