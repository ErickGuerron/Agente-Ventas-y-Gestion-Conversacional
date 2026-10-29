"""Long-polling runner for local interactive testing of the Telegram bot."""

import asyncio

from aiogram import Bot, Dispatcher, types
from sqlalchemy.orm import Session

from modules.ai_engine.factory import get_llm_client, get_sales_graph
from modules.channels.dto import IncomingMessage
from modules.channels.telegram_service import TelegramChannelService
from modules.conversations.repository import ConversationRepository
from shared.config.settings import get_settings
from shared.database.session import get_engine


async def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        print("[ERROR] TELEGRAM_BOT_TOKEN is not configured in backend/.env")
        return

    print(
        f"[POLLING] Starting Telegram bot polling with token {settings.telegram_bot_token[:10]}..."
    )
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()
    engine = get_engine()
    service = TelegramChannelService(bot=bot)
    llm = get_llm_client()
    graph = get_sales_graph(llm=llm)

    @dp.message()
    async def handle_message(message: types.Message) -> None:
        if not message.text:
            return

        chat_id = str(message.chat.id)
        msg_id = str(message.message_id)
        name = message.from_user.full_name if message.from_user else None
        username = message.from_user.username if message.from_user else None

        incoming = IncomingMessage(
            channel="telegram",
            external_chat_id=chat_id,
            external_message_id=msg_id,
            text=message.text.strip(),
            sender_name=name,
            username=username,
        )

        with Session(engine) as session:
            repo = ConversationRepository(session)
            sender_info = f"{incoming.sender_name} ({incoming.external_chat_id})"
            print(f"[TG IN] From {sender_info}: {incoming.text}")
            reply = await service.process_incoming_message(incoming, repo, llm=llm, graph=graph)
            session.commit()
            if reply:
                print(f"[TG OUT] Sent reply: {reply}")
            else:
                print("[TG] Silence (HUMAN_ACTIVE / Handover)")

    print("[POLLING] Bot is running and waiting for messages! (Press Ctrl+C to stop)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
