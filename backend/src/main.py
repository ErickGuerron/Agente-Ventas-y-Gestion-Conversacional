"""FastAPI entry point. Webhooks, REST and WebSocket routes are added by their modules."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from modules.channels.routes import router as telegram_router
from modules.conversations.routes import router as conversations_router

app = FastAPI(title="Hackathon UTA bot")

# Enable CORS for local and dashboard frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(telegram_router, prefix="/api/telegram", tags=["channels"])
app.include_router(conversations_router, prefix="/api/conversations", tags=["conversations"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
