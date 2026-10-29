"""REST and WebSocket routes for conversations, handover, and operator actions."""

import uuid
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from modules.channels.routes import get_telegram_service
from modules.channels.telegram_service import TelegramChannelService
from modules.conversations.repository import ConversationRepository
from shared.database.session import get_db_session
from shared.security.operator_auth import authorize_operator_websocket, require_operator
from shared.websocket.manager import connection_manager

# HTTP routes require the operator header. The WebSocket has its own router because router-level
# HTTP dependencies also apply to WebSocket handshakes, which carry the key as ?token= instead.
router = APIRouter(dependencies=[Depends(require_operator)])
websocket_router = APIRouter()


class TransitionRequest(BaseModel):
    expected_version: int | None = None
    owner_id: str | None = None


class OperatorReplyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.get("")
def list_conversations(
    session: Annotated[Session, Depends(get_db_session)],
) -> list[dict[str, Any]]:
    """List all active conversations with their latest message and status."""
    repo = ConversationRepository(session)
    conversations = repo.list_active_conversations()
    leads = repo.latest_leads_by_conversation()
    output = []
    for conv in conversations:
        recent = repo.list_recent_messages(conv.id, limit=1)
        last_msg = recent[-1] if recent else None
        output.append(
            {
                "id": str(conv.id),
                "channel": conv.channel,
                "external_chat_id": conv.external_chat_id,
                "status": conv.status,
                "version": conv.version,
                "lead_status": leads.get(str(conv.id)),
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "last_message": last_msg.content if last_msg else None,
                "last_sender_type": last_msg.sender_type if last_msg else None,
                "last_message_at": (
                    last_msg.created_at.isoformat() if last_msg and last_msg.created_at else None
                ),
            }
        )
    return output


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: str,
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, Any]:
    """One conversation with its AI/Human state and commercial thermometer."""
    repo = ConversationRepository(session)
    conv = repo.get_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return {
        "id": str(conv.id),
        "channel": conv.channel,
        "external_chat_id": conv.external_chat_id,
        "status": conv.status,
        "version": conv.version,
        "lead_status": repo.latest_leads_by_conversation().get(str(conv.id)),
    }


@router.get("/{conversation_id}/messages")
def list_conversation_messages(
    conversation_id: str,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[dict[str, Any]]:
    """Fetch message history for a conversation ordered chronologically."""
    repo = ConversationRepository(session)
    conv = repo.get_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    messages = repo.list_recent_messages(conv.id, limit=100)
    return [
        {
            "id": str(msg.id),
            "conversation_id": str(msg.conversation_id),
            "sender_type": msg.sender_type,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }
        for msg in messages
    ]


@router.post("/{conversation_id}/takeover")
async def takeover_conversation(
    conversation_id: str,
    payload: TransitionRequest | None = None,
    session: Annotated[Session, Depends(get_db_session)] = None,
) -> dict[str, Any]:
    """Human operator takes control of conversation (changes status to HUMAN_ACTIVE)."""
    repo = ConversationRepository(session)
    conv = repo.get_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    expected_version = (
        payload.expected_version
        if payload and payload.expected_version is not None
        else conv.version
    )
    owner_uuid = uuid.UUID(payload.owner_id) if payload and payload.owner_id else None

    success = repo.transition_status(
        conversation_id=conv.id,
        expected_version=expected_version,
        new_status="HUMAN_ACTIVE",
        owner_id=owner_uuid,
        event_payload={"action": "operator_takeover"},
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict: Conversation version has changed or was modified concurrently",
        )

    session.commit()

    updated_conv = repo.get_by_id(conv.id)
    new_ver = updated_conv.version if updated_conv else expected_version + 1

    await connection_manager.broadcast(
        {
            "event": "status_changed",
            "conversation_id": str(conv.id),
            "status": "HUMAN_ACTIVE",
            "version": new_ver,
        }
    )

    return {
        "ok": True,
        "conversation_id": str(conv.id),
        "status": "HUMAN_ACTIVE",
        "version": new_ver,
    }


@router.post("/{conversation_id}/resume")
async def resume_conversation(
    conversation_id: str,
    payload: TransitionRequest | None = None,
    session: Annotated[Session, Depends(get_db_session)] = None,
) -> dict[str, Any]:
    """Resume automatic AI responses for the conversation (changes status to AI_ACTIVE)."""
    repo = ConversationRepository(session)
    conv = repo.get_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    expected_version = (
        payload.expected_version
        if payload and payload.expected_version is not None
        else conv.version
    )

    success = repo.transition_status(
        conversation_id=conv.id,
        expected_version=expected_version,
        new_status="AI_ACTIVE",
        owner_id=None,
        event_payload={"action": "operator_resumed_ai"},
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict: Conversation version has changed or was modified concurrently",
        )

    session.commit()

    updated_conv = repo.get_by_id(conv.id)
    new_ver = updated_conv.version if updated_conv else expected_version + 1

    await connection_manager.broadcast(
        {
            "event": "status_changed",
            "conversation_id": str(conv.id),
            "status": "AI_ACTIVE",
            "version": new_ver,
        }
    )

    return {
        "ok": True,
        "conversation_id": str(conv.id),
        "status": "AI_ACTIVE",
        "version": new_ver,
    }


@router.post("/{conversation_id}/reply")
async def operator_reply(
    conversation_id: str,
    payload: OperatorReplyRequest,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[TelegramChannelService, Depends(get_telegram_service)],
) -> dict[str, Any]:
    """Human operator sends a reply message to the prospect via Telegram."""
    repo = ConversationRepository(session)
    conv = repo.get_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    # Operators may only write while they hold the conversation (handover). Otherwise an
    # operator reply could interleave with AI replies that are still being generated.
    if conv.status != "HUMAN_ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Take control of the conversation before replying",
        )

    # 1. Persist operator message
    msg = repo.add_message(
        conversation_id=conv.id,
        sender_type="operator",
        content=payload.text.strip(),
    )
    session.commit()

    # 2. Dispatch to Telegram
    if conv.channel == "telegram":
        await service.send_message(conv.external_chat_id, payload.text.strip())

    # 3. Broadcast to all open dashboard WebSockets
    await connection_manager.broadcast(
        {
            "event": "message_sent",
            "conversation_id": str(conv.id),
            "sender_type": "operator",
            "content": payload.text.strip(),
            "message_id": str(msg.id),
        }
    )

    return {"ok": True, "message_id": str(msg.id)}


@websocket_router.websocket("/ws")
async def websocket_operator_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time operator notifications and chats."""
    if not await authorize_operator_websocket(websocket):
        return
    await connection_manager.connect(websocket)
    try:
        while True:
            # Keep connection open; receive ping or operator status
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception:
        connection_manager.disconnect(websocket)
