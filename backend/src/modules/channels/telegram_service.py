"""Telegram channel adapter using aiogram.

Handles message parsing, sending, and dispatching to ConversationRepository and LLM.
"""

from typing import Any

from aiogram import Bot

from modules.ai_engine.ports import LLMClient
from modules.channels.dto import IncomingMessage
from modules.conversations.repository import ConversationRepository


class TelegramChannelService:
    def __init__(self, token: str = "", bot: Bot | None = None) -> None:
        if bot is not None:
            self._bot = bot
        elif token:
            try:
                self._bot = Bot(token=token)
            except Exception:
                self._bot = None
        else:
            self._bot = None

    @property
    def bot(self) -> Bot:
        if self._bot is None:
            raise ValueError(
                "Telegram Bot is not configured (missing or invalid TELEGRAM_BOT_TOKEN)"
            )
        return self._bot

    def parse_update(self, payload: dict[str, Any]) -> IncomingMessage | None:
        """Extract domain IncomingMessage from Telegram update dictionary."""
        message_data = payload.get("message")
        if not message_data or not isinstance(message_data, dict):
            return None

        text = message_data.get("text")
        if not text:
            # Ignore non-text updates (photos, stickers, etc.)
            return None

        chat_data = message_data.get("chat", {})
        chat_id = chat_data.get("id")
        if chat_id is None:
            return None

        message_id = message_data.get("message_id")
        from_data = message_data.get("from", {})
        first_name = from_data.get("first_name", "")
        last_name = from_data.get("last_name", "")
        full_name = f"{first_name} {last_name}".strip() or None
        username = from_data.get("username")

        return IncomingMessage(
            channel="telegram",
            external_chat_id=str(chat_id),
            external_message_id=str(message_id) if message_id is not None else "",
            text=text.strip(),
            sender_name=full_name,
            username=username,
        )

    async def send_message(self, external_chat_id: str, text: str) -> None:
        """Send message back to user via Telegram Bot API."""
        chat_id = int(external_chat_id)
        await self.bot.send_message(chat_id=chat_id, text=text)

    async def process_incoming_message(
        self,
        incoming: IncomingMessage,
        repo: ConversationRepository,
        llm: LLMClient,
    ) -> str | None:
        """
        Process incoming telegram message:
        1. Ensure conversation exists in Supabase.
        2. Persist user message.
        3. If AI_ACTIVE, generate LLM response, persist it, and dispatch via Telegram.
        4. If HUMAN_ACTIVE, keep silence so the operator can reply from Dashboard.
        """
        conv = repo.get_or_create(incoming.channel, incoming.external_chat_id)
        repo.add_message(
            conversation_id=conv.id,
            sender_type="user",
            content=incoming.text,
            external_message_id=incoming.external_message_id or None,
        )

        if conv.status != "AI_ACTIVE":
            return None

        reply_text = llm.generate(incoming.text)
        repo.add_message(
            conversation_id=conv.id,
            sender_type="ai",
            content=reply_text,
        )

        await self.send_message(incoming.external_chat_id, reply_text)
        return reply_text
