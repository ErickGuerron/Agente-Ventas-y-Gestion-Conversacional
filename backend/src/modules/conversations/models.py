"""SQLAlchemy models matching the official Supabase schema."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from shared.database.base import Base

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
UUID_TYPE = UUID(as_uuid=True)


def utc_now() -> datetime:
    return datetime.now(UTC)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("channel", "external_chat_id", name="uq_channel_chat_id"),
        Index("ix_conversations_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(String, default="telegram", nullable=False)
    external_chat_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, default="AI_ACTIVE", nullable=False
    )  # "AI_ACTIVE", "HUMAN_ACTIVE"
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID_TYPE, ForeignKey("operators.id"), nullable=True
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )  # Concurrency control for handover
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    # Relationships
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    leads: Mapped[list["Lead"]] = relationship(
        "Lead", back_populates="conversation", cascade="all, delete-orphan"
    )
    events: Mapped[list["ConversationEvent"]] = relationship(
        "ConversationEvent", back_populates="conversation", cascade="all, delete-orphan"
    )
    owner: Mapped["Operator | None"] = relationship("Operator")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conv_id", "conversation_id"),
        Index("ix_messages_external_id", "external_message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    external_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    sender_type: Mapped[str] = mapped_column(String, nullable=False)  # "user", "ai", "operator"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    analysis: Mapped["ConversationAnalysis | None"] = relationship(
        "ConversationAnalysis",
        back_populates="message",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (Index("ix_leads_conv_id", "conversation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    interested_course: Mapped[str | None] = mapped_column(String, nullable=True)
    stage: Mapped[str] = mapped_column(
        String, default="INTERESADO", nullable=False
    )  # "INTERESADO", "DUDOSO", "FRUSTRADO", "LEAD_CALIENTE"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="leads")


class ConversationAnalysis(Base):
    __tablename__ = "conversation_analysis"
    __table_args__ = (Index("ix_analysis_msg_id", "message_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    intent: Mapped[str] = mapped_column(
        String, nullable=False
    )  # "ACADEMICO", "COMERCIAL", "FRUSTRACION"
    lead_status: Mapped[str] = mapped_column(
        String, nullable=False
    )  # "INTERESADO", "DUDOSO", "FRUSTRADO", "LEAD_CALIENTE"
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    token_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    message: Mapped["Message"] = relationship("Message", back_populates="analysis")


class ConversationEvent(Base):
    __tablename__ = "conversation_events"
    __table_args__ = (Index("ix_events_conv_id", "conversation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="events")


class Operator(Base):
    __tablename__ = "operators"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, default="operator", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_available", "status", "available_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String, default="PENDING", nullable=False
    )  # "PENDING", "RUNNING", "DONE", "FAILED"
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
