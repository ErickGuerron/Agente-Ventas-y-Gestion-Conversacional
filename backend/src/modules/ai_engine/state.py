"""State of the sales graph (architecture section 6)."""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

INTENTS = ("academic", "sales", "unknown")
LEAD_STATUSES = ("INTERESADO", "DUDOSO", "FRUSTRADO", "LEAD_CALIENTE")


class GraphState(TypedDict, total=False):
    conversation_id: str
    messages: Annotated[list[AnyMessage], add_messages]
    intent: str
    lead_status: str
    selected_agent: str
    requires_human: bool
    response: str
    analysis: dict
