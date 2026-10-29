"""FastAPI entry point. Webhooks, REST and WebSocket routes are added by their modules."""

from fastapi import FastAPI

from modules.channels.routes import router as telegram_router

app = FastAPI(title="Hackathon UTA bot")

app.include_router(telegram_router, prefix="/api/telegram", tags=["channels"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
