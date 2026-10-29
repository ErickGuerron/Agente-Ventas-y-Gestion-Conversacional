"""FastAPI entry point. Webhooks, REST and WebSocket routes are added by their modules."""

from fastapi import FastAPI

app = FastAPI(title="Hackathon UTA bot")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
