"""Sales graph (architecture section 6).

analyze -> route_decision -> academic_agent | sales_agent | human_review -> persist_analysis

Routing is deterministic: the LLM only classifies. Frustration always hands off to a human.
Persisting the analysis to PostgreSQL is delegated to the conversations port; this graph
only produces the record in ``analysis``.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from modules.ai_engine.classifier import parse_analysis
from modules.ai_engine.ports import LLMClient
from modules.ai_engine.prompts import analysis_prompt, answer_prompt
from modules.ai_engine.state import GraphState
from modules.courses.catalog import Course

HUMAN_HANDOFF_TEXT = "Un asesor de nuestro equipo te atenderá en breve."
NO_PROMOTION_TEXT = (
    "No tengo promociones autorizadas para esa consulta. "
    "Puedo compartirte el precio oficial del curso."
)
_UNAUTHORIZED_OFFER = re.compile(r"descuento|rebaja|gratis|gratuit|%", re.IGNORECASE)
_HISTORY_LIMIT = 10


def _current_user_text(state: GraphState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def _history(messages: list[AnyMessage]) -> str:
    lines = []
    for message in messages[-_HISTORY_LIMIT:]:
        speaker = "Usuario" if isinstance(message, HumanMessage) else "Asistente"
        lines.append(f"{speaker}: {message.content}")
    return "\n".join(lines)


def route_decision(state: GraphState) -> str:
    if state.get("requires_human"):
        return "human_review"
    if state.get("intent") == "sales":
        return "sales_agent"
    return "academic_agent"


def _make_analyze(llm: LLMClient):
    def analyze(state: GraphState) -> dict[str, Any]:
        analysis = parse_analysis(llm.generate(analysis_prompt(_current_user_text(state))))
        return {
            "intent": analysis["intent"],
            "lead_status": analysis["lead_status"],
            "requires_human": analysis["lead_status"] == "FRUSTRADO",
        }

    return analyze


def _make_academic(llm: LLMClient, catalog: list[Course]):
    def academic_agent(state: GraphState) -> dict[str, Any]:
        prior = _history(state["messages"][:-1])
        reply = llm.generate(answer_prompt("académico", catalog, prior, _current_user_text(state)))
        return {
            "response": reply,
            "selected_agent": "academic_agent",
            "messages": [AIMessage(content=reply)],
        }

    return academic_agent


def _make_sales(llm: LLMClient, catalog: list[Course]):
    has_authorized_promotions = any(c.promociones_autorizadas for c in catalog)

    def sales_agent(state: GraphState) -> dict[str, Any]:
        prior = _history(state["messages"][:-1])
        reply = llm.generate(answer_prompt("comercial", catalog, prior, _current_user_text(state)))
        # Deterministic guard: the LLM may not promise discounts the catalog does not authorize.
        if not has_authorized_promotions and _UNAUTHORIZED_OFFER.search(reply):
            reply = NO_PROMOTION_TEXT
        return {
            "response": reply,
            "selected_agent": "sales_agent",
            "messages": [AIMessage(content=reply)],
        }

    return sales_agent


def human_review(state: GraphState) -> dict[str, Any]:
    return {
        "response": HUMAN_HANDOFF_TEXT,
        "selected_agent": "human_review",
        "requires_human": True,
        "messages": [AIMessage(content=HUMAN_HANDOFF_TEXT)],
    }


def persist_analysis(state: GraphState) -> dict[str, Any]:
    analysis = {
        "intent": state.get("intent", "unknown"),
        "lead_status": state.get("lead_status", "DUDOSO"),
        "selected_agent": state.get("selected_agent", ""),
        "requires_human": state.get("requires_human", False),
    }
    return {"analysis": analysis}


def build_graph(llm: LLMClient, catalog: list[Course], checkpointer: Any = None):
    """Compile the sales graph. Pass a ``thread_id`` in the config on every invoke."""
    builder = StateGraph(GraphState)
    builder.add_node("analyze", _make_analyze(llm))
    builder.add_node("academic_agent", _make_academic(llm, catalog))
    builder.add_node("sales_agent", _make_sales(llm, catalog))
    builder.add_node("human_review", human_review)
    builder.add_node("persist_analysis", persist_analysis)

    builder.add_edge(START, "analyze")
    builder.add_conditional_edges(
        "analyze",
        route_decision,
        {
            "academic_agent": "academic_agent",
            "sales_agent": "sales_agent",
            "human_review": "human_review",
        },
    )
    builder.add_edge("academic_agent", "persist_analysis")
    builder.add_edge("sales_agent", "persist_analysis")
    builder.add_edge("human_review", "persist_analysis")
    builder.add_edge("persist_analysis", END)

    return builder.compile(checkpointer=checkpointer or InMemorySaver())
