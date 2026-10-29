"""promptfoo provider: runs the real LangGraph sales graph with Gemini.

promptfoo calls ``call_api`` once per test case. Each case gets its own thread so the
conversations never share memory.
"""

import sys
import uuid
from pathlib import Path
from typing import Any

BACKEND_SRC = Path(__file__).resolve().parents[1] / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from langchain_core.messages import HumanMessage  # noqa: E402

from modules.ai_engine.graph import build_graph  # noqa: E402
from modules.ai_engine.llm_factory import build_llm_client  # noqa: E402
from modules.courses.catalog import load_catalog  # noqa: E402
from shared.config.settings import get_settings  # noqa: E402

_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph(build_llm_client(get_settings()), load_catalog())
    return _GRAPH


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    question = str(context["vars"]["question"])
    thread = f"eval:{uuid.uuid4()}"
    try:
        result = _graph().invoke(
            {"messages": [HumanMessage(content=question)], "conversation_id": thread},
            config={"configurable": {"thread_id": thread}},
        )
    except Exception as error:  # surfaced to promptfoo as a test error, not a crash
        return {"error": f"{type(error).__name__}: {error}"}
    return {"output": result["response"]}
