"""FastAPI entry point. Webhooks, REST and WebSocket routes are added by their modules."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from modules.channels.routes import router as telegram_router
from modules.conversations.routes import router as conversations_router
from modules.conversations.routes import websocket_router as conversations_ws_router
from shared.config.settings import get_settings

app = FastAPI(title="Hackathon UTA bot")

# Only the configured dashboard origins may call the API from a browser. The operator key is
# sent in a header, so cookies (allow_credentials) are not needed and stay off.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-Operator-Key", "Content-Type"],
)

app.include_router(telegram_router, prefix="/api/telegram", tags=["channels"])
app.include_router(conversations_router, prefix="/api/conversations", tags=["conversations"])
app.include_router(conversations_ws_router, prefix="/api/conversations")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
