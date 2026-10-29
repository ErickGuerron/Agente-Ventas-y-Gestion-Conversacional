"""Telegram channel adapter using aiogram.

Handles message parsing, sending, and dispatching to ConversationRepository and LangGraph.
"""

import time
from typing import Any

from aiogram import Bot
from langchain_core.messages import HumanMessage

from modules.ai_engine.factory import get_sales_graph
from modules.ai_engine.ports import LLMClient
from modules.channels.dto import IncomingMessage
from modules.conversations.repository import ConversationRepository


class TelegramChannelService:
    def __init__(
        self,
        token: str = "",
        bot: Bot | None = None,
        graph: Any | None = None,
    ) -> None:
        self._graph = graph
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
        llm: LLMClient | None = None,
        graph: Any | None = None,
    ) -> str | None:
        """
        Process incoming telegram message:
        1. Ensure conversation exists in Supabase.
        2. Persist user message.
        3. If HUMAN_ACTIVE, keep silence so the operator can reply from Dashboard.
        4. If AI_ACTIVE:
           a. Invoke sales multi-agent LangGraph (Academic, Sales or Human Review).
           b. If requires_human (frustration): atómicamente transition to HUMAN_ACTIVE,
              persist audit event and analysis, and dispatch handover message.
           c. If not requires_human: verify race conditions (discard if operator took control),
              persist analysis and AI reply, and dispatch to Telegram.
        """
        conv = repo.get_or_create(incoming.channel, incoming.external_chat_id)
        user_msg = repo.add_message(
            conversation_id=conv.id,
            sender_type="user",
            content=incoming.text,
            external_message_id=incoming.external_message_id or None,
        )

        if conv.status != "AI_ACTIVE":
            return None

        active_graph = graph or self._graph
        if active_graph is None:
            active_graph = get_sales_graph(llm=llm)

        thread_id = f"telegram:{incoming.external_chat_id}"
        start_t = time.perf_counter()
        graph_result = active_graph.invoke(
            {
                "messages": [HumanMessage(content=incoming.text)],
                "conversation_id": thread_id,
            },
            config={"configurable": {"thread_id": thread_id}},
        )
        latency_ms = int((time.perf_counter() - start_t) * 1000)

        reply_text = str(graph_result.get("response", ""))
        requires_human = bool(graph_result.get("requires_human", False))
        selected_agent = str(graph_result.get("selected_agent", ""))
        analysis = graph_result.get("analysis", {})
        intent = analysis.get("intent", "unknown")
        lead_status = analysis.get("lead_status", "DUDOSO")

        user_msg_id = getattr(user_msg, "id", None)

        if requires_human:
            # Atomic transition to HUMAN_ACTIVE with optimistic lock
            conv_version = getattr(conv, "version", 1)
            if hasattr(repo, "transition_status"):
                repo.transition_status(
                    conversation_id=conv.id,
                    expected_version=conv_version,
                    new_status="HUMAN_ACTIVE",
                    event_payload={
                        "reason": "frustration_or_human_handoff",
                        "selected_agent": selected_agent,
                        "analysis": analysis,
                    },
                )

            if user_msg_id and hasattr(repo, "save_analysis"):
                try:
                    repo.save_analysis(
                        message_id=user_msg_id,
                        intent=intent,
                        lead_status=lead_status,
                        latency_ms=latency_ms,
                    )
                except Exception:
                    pass

            repo.add_message(
                conversation_id=conv.id,
                sender_type="ai",
                content=reply_text,
            )
            await self.send_message(incoming.external_chat_id, reply_text)
            return reply_text

        # Race condition check: verify if an operator took control while LLM was processing
        current_conv = repo.get_by_id(conv.id) if hasattr(repo, "get_by_id") else conv
        if current_conv and (
            current_conv.status != "AI_ACTIVE"
            or getattr(current_conv, "version", 1) != getattr(conv, "version", 1)
        ):
            return None

        if user_msg_id and hasattr(repo, "save_analysis"):
            try:
                repo.save_analysis(
                    message_id=user_msg_id,
                    intent=intent,
                    lead_status=lead_status,
                    latency_ms=latency_ms,
                )
            except Exception:
                pass

        repo.add_message(
            conversation_id=conv.id,
            sender_type="ai",
            content=reply_text,
        )
        await self.send_message(incoming.external_chat_id, reply_text)
        return reply_text
