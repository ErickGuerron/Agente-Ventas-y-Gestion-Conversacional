"""Telegram Webhook route."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from modules.ai_engine.factory import get_llm_client
from modules.ai_engine.ports import LLMClient
from modules.channels.telegram_service import TelegramChannelService
from modules.conversations.repository import ConversationRepository
from shared.config.settings import Settings, get_settings
from shared.database.session import get_db_session

router = APIRouter()


def get_telegram_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> TelegramChannelService:
    return TelegramChannelService(token=settings.telegram_bot_token)


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    secret_token: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
    service: Annotated[TelegramChannelService, Depends(get_telegram_service)] = None,
    session: Annotated[Session, Depends(get_db_session)] = None,
    llm: Annotated[LLMClient, Depends(get_llm_client)] = None,
) -> dict[str, Any]:
    # 1. Validate secret token if configured
    if settings and settings.telegram_webhook_secret:
        if secret_token != settings.telegram_webhook_secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Telegram webhook secret",
            )

    # 2. Extract JSON payload
    try:
        payload = await request.json()
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from err

    # 3. Parse update
    incoming = service.parse_update(payload)
    if not incoming:
        return {"ok": True, "skipped": True}

    # 4. Process and dispatch message
    repo = ConversationRepository(session)
    reply = await service.process_incoming_message(incoming, repo, llm=llm)

    return {"ok": True, "reply_generated": bool(reply)}
