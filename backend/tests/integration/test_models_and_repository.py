"""Integration tests for Conversation models and repository against live PostgreSQL / Supabase."""

import uuid

import pytest
from sqlalchemy.orm import Session

from modules.conversations.models import Operator
from modules.conversations.repository import ConversationRepository
from shared.database.base import Base
from shared.database.engine import make_engine


@pytest.fixture
def db_session(database_url: str):
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session
        session.rollback()


@pytest.mark.integration
def test_create_tables_and_get_or_create(db_session: Session) -> None:
    repo = ConversationRepository(db_session)
    test_chat_id = f"test_chat_{uuid.uuid4().hex[:8]}"

    # First call: creates conversation
    conv1 = repo.get_or_create("telegram", test_chat_id)
    assert conv1.id is not None
    assert conv1.channel == "telegram"
    assert conv1.external_chat_id == test_chat_id
    assert conv1.status == "AI_ACTIVE"
    assert conv1.version == 1

    # Second call: returns existing conversation
    conv2 = repo.get_or_create("telegram", test_chat_id)
    assert conv2.id == conv1.id

    # Clean up test row
    db_session.delete(conv1)
    db_session.commit()


@pytest.mark.integration
def test_messages_history_flow(db_session: Session) -> None:
    repo = ConversationRepository(db_session)
    test_chat_id = f"test_flow_{uuid.uuid4().hex[:8]}"
    conv = repo.get_or_create("telegram", test_chat_id)
    db_session.commit()

    msg1 = repo.add_message(conv.id, "user", "¿Cuál es el precio de Python?", "ext_1")
    msg2 = repo.add_message(conv.id, "ai", "El curso de Python cuesta $80 USD.", "ext_2")
    db_session.commit()

    assert msg1.id is not None
    assert msg2.id is not None

    recent = repo.list_recent_messages(conv.id, limit=10)
    assert len(recent) == 2
    assert recent[0].content == "¿Cuál es el precio de Python?"
    assert recent[1].content == "El curso de Python cuesta $80 USD."

    # Analysis record
    analysis = repo.save_analysis(
        message_id=msg1.id,
        intent="ACADEMICO",
        lead_status="INTERESADO",
        latency_ms=450,
        token_usage=120,
    )
    db_session.commit()
    assert analysis.id is not None
    assert analysis.intent == "ACADEMICO"
    assert analysis.lead_status == "INTERESADO"

    # Clean up
    db_session.delete(conv)
    db_session.commit()


@pytest.mark.integration
def test_handover_transition_concurrency(db_session: Session) -> None:
    repo = ConversationRepository(db_session)
    test_chat_id = f"test_ho_{uuid.uuid4().hex[:8]}"
    conv = repo.get_or_create("telegram", test_chat_id)
    db_session.commit()

    # Create operator for foreign key validity
    operator_uuid = uuid.uuid4()
    operator = Operator(id=operator_uuid, display_name="Operador Test", role="operator")
    db_session.add(operator)
    db_session.commit()

    # 1. Normal transition: expected_version=1 -> HUMAN_ACTIVE
    success = repo.transition_status(
        conversation_id=conv.id,
        expected_version=1,
        new_status="HUMAN_ACTIVE",
        owner_id=operator_uuid,
        event_payload={"reason": "operator_takeover"},
    )
    db_session.commit()
    assert success is True

    # Refresh
    refreshed = repo.get_by_id(conv.id)
    assert refreshed is not None
    assert refreshed.status == "HUMAN_ACTIVE"
    assert refreshed.version == 2
    assert refreshed.owner_id == operator_uuid

    # 2. Stale transition attempt: trying with old expected_version=1 must fail
    conflict_success = repo.transition_status(
        conversation_id=conv.id,
        expected_version=1,
        new_status="AI_ACTIVE",
    )
    assert conflict_success is False

    # 3. Transition with current version=2 succeeds
    resume_success = repo.transition_status(
        conversation_id=conv.id,
        expected_version=2,
        new_status="AI_ACTIVE",
    )
    db_session.commit()
    assert resume_success is True

    final_conv = repo.get_by_id(conv.id)
    assert final_conv is not None
    assert final_conv.status == "AI_ACTIVE"
    assert final_conv.version == 3

    # Clean up
    db_session.delete(conv)
    db_session.delete(operator)
    db_session.commit()
