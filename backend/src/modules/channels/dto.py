"""Data Transfer Objects for external messaging channels."""

from pydantic import BaseModel


class IncomingMessage(BaseModel):
    channel: str = "telegram"
    external_chat_id: str
    external_message_id: str
    text: str
    sender_name: str | None = None
    username: str | None = None


class OutgoingMessage(BaseModel):
    channel: str = "telegram"
    external_chat_id: str
    text: str
