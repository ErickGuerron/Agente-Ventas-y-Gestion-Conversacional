"""Repository for conversations, messages and handover transitions.

Encapsulates all database interactions for the conversations bounded context.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from modules.conversations.models import (
    Conversation,
    ConversationAnalysis,
    ConversationEvent,
    Job,
    Message,
)


def _to_uuid(val: uuid.UUID | str | None) -> uuid.UUID | None:
    if val is None:
        return None
    return uuid.UUID(str(val)) if isinstance(val, str) else val


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create(self, channel: str, external_chat_id: str) -> Conversation:
        """Fetch an existing conversation or create a new one atomically."""
        stmt = select(Conversation).where(
            Conversation.channel == channel,
            Conversation.external_chat_id == str(external_chat_id),
        )
        conv = self.session.scalars(stmt).first()
        if conv:
            return conv

        conv = Conversation(
            channel=channel,
            external_chat_id=str(external_chat_id),
            status="AI_ACTIVE",
            version=1,
        )
        self.session.add(conv)
        self.session.flush()
        return conv

    def get_by_id(self, conversation_id: uuid.UUID | str) -> Conversation | None:
        """Fetch conversation by primary key."""
        uid = _to_uuid(conversation_id)
        return self.session.get(Conversation, uid)

    def add_message(
        self,
        conversation_id: uuid.UUID | str,
        sender_type: str,
        content: str,
        external_message_id: str | None = None,
    ) -> Message:
        """Record an incoming or outgoing message in the conversation history."""
        uid = _to_uuid(conversation_id)
        ext_id = str(external_message_id) if external_message_id else str(uuid.uuid4())
        if external_message_id:
            existing = self.session.scalars(
                select(Message).where(
                    Message.conversation_id == uid,
                    Message.external_message_id == ext_id,
                )
            ).first()
            if existing:
                return existing

        message = Message(
            conversation_id=uid,
            sender_type=sender_type,
            content=content,
            external_message_id=ext_id,
        )
        self.session.add(message)
        self.session.flush()
        return message

    def transition_status(
        self,
        conversation_id: uuid.UUID | str,
        expected_version: int,
        new_status: str,
        owner_id: uuid.UUID | str | None = None,
        event_payload: dict[str, Any] | None = None,
    ) -> bool:
        """Transition status (e.g. AI_ACTIVE -> HUMAN_ACTIVE) using optimistic locking.

        Returns True if successful, or False if another process modified the conversation.
        """
        cid = _to_uuid(conversation_id)
        oid = _to_uuid(owner_id)

        stmt = (
            update(Conversation)
            .where(
                Conversation.id == cid,
                Conversation.version == expected_version,
            )
            .values(
                status=new_status,
                owner_id=oid,
                version=Conversation.version + 1,
            )
        )
        result = self.session.execute(stmt)
        if result.rowcount == 0:
            return False

        # Record audit event
        event = ConversationEvent(
            conversation_id=cid,
            type=f"status_changed_to_{new_status.lower()}",
            payload=event_payload or {},
        )
        self.session.add(event)
        self.session.flush()
        return True

    def save_analysis(
        self,
        message_id: uuid.UUID | str,
        intent: str,
        lead_status: str,
        latency_ms: int = 0,
        token_usage: int = 0,
    ) -> ConversationAnalysis:
        """Persist AI metrics and intent classification for a processed message."""
        mid = _to_uuid(message_id)
        analysis = ConversationAnalysis(
            message_id=mid,
            intent=intent,
            lead_status=lead_status,
            latency_ms=latency_ms,
            token_usage=token_usage,
        )
        self.session.add(analysis)
        self.session.flush()
        return analysis

    def list_recent_messages(
        self, conversation_id: uuid.UUID | str, limit: int = 50
    ) -> list[Message]:
        """Fetch the latest messages ordered chronologically."""
        cid = _to_uuid(conversation_id)
        stmt = (
            select(Message)
            .where(Message.conversation_id == cid)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = list(self.session.scalars(stmt).all())
        messages.reverse()
        return messages

    def list_active_conversations(self) -> list[Conversation]:
        """Fetch all active conversations for the dashboard view."""
        stmt = select(Conversation).order_by(Conversation.created_at.desc())
        return list(self.session.scalars(stmt).all())

    def latest_leads_by_conversation(self) -> dict[str, str]:
        """Latest commercial thermometer per conversation, keyed by conversation id string."""
        stmt = (
            select(Message.conversation_id, ConversationAnalysis.lead_status)
            .join(ConversationAnalysis, ConversationAnalysis.message_id == Message.id)
            .order_by(Message.created_at.asc(), ConversationAnalysis.created_at.asc())
        )
        latest: dict[str, str] = {}
        for conversation_id, lead_status in self.session.execute(stmt).all():
            latest[str(conversation_id)] = lead_status
        return latest

    def analysis_points(self) -> list[tuple[str, int, int]]:
        """(intent, latency_ms, token_usage) for every analyzed message."""
        stmt = select(
            ConversationAnalysis.intent,
            ConversationAnalysis.latency_ms,
            ConversationAnalysis.token_usage,
        )
        return [tuple(row) for row in self.session.execute(stmt).all()]

    def message_times_since(self, since: datetime) -> list[datetime]:
        """Creation times of messages not older than ``since``."""
        stmt = select(Message.created_at).where(Message.created_at >= since)
        return list(self.session.scalars(stmt).all())

    def failed_jobs_count(self) -> int:
        """Jobs that exhausted their retries; the worker is the only writer of this status."""
        stmt = select(func.count()).select_from(Job).where(Job.status == "FAILED")
        return int(self.session.scalar(stmt) or 0)
