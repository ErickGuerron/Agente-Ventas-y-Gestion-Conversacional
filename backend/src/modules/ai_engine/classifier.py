"""Parses the structured analysis returned by the LLM, falling back to safe defaults."""

import json
import re
from typing import Any

from modules.ai_engine.state import INTENTS, LEAD_STATUSES

DEFAULT_ANALYSIS: dict[str, str] = {"intent": "unknown", "lead_status": "DUDOSO"}
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def parse_analysis(raw: str) -> dict[str, str]:
    match = _JSON_OBJECT.search(raw)
    if match is None:
        return dict(DEFAULT_ANALYSIS)
    try:
        data: Any = json.loads(match.group(0))
    except json.JSONDecodeError:
        return dict(DEFAULT_ANALYSIS)
    if not isinstance(data, dict):
        return dict(DEFAULT_ANALYSIS)

    intent = data.get("intent")
    lead_status = data.get("lead_status")
    return {
        "intent": intent if intent in INTENTS else DEFAULT_ANALYSIS["intent"],
        "lead_status": lead_status
        if lead_status in LEAD_STATUSES
        else DEFAULT_ANALYSIS["lead_status"],
    }
