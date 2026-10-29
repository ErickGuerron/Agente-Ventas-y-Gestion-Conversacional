"""Aggregates persisted conversation data into the operator dashboard metrics.

Pure functions only: the repository loads the rows, this module counts them. Timestamps are
compared as naive UTC, because the database columns are naive.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

HOT_LEAD = "LEAD_CALIENTE"
HUMAN_CONTROLLED = "HUMAN_ACTIVE"
WINDOW_HOURS = 24


@dataclass(frozen=True)
class AnalysisPoint:
    intent: str
    latency_ms: int
    token_usage: int


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _hour_floor(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def build_summary(
    *,
    statuses: list[str],
    latest_lead_by_conversation: dict[str, str],
    analyses: list[AnalysisPoint],
    message_times: list[datetime],
    failed_jobs: int,
    now: datetime,
) -> dict[str, Any]:
    now_utc = _naive_utc(now)
    current_hour = _hour_floor(now_utc)
    window_start = current_hour - timedelta(hours=WINDOW_HOURS - 1)

    counts = Counter(_naive_utc(t) for t in message_times)
    buckets = []
    for offset in range(WINDOW_HOURS):
        hour = window_start + timedelta(hours=offset)
        in_hour = sum(count for stamp, count in counts.items() if _hour_floor(stamp) == hour)
        buckets.append({"hour": hour.isoformat(), "count": in_hour})

    measured = [point.latency_ms for point in analyses if point.latency_ms > 0]
    return {
        "active_conversations": len(statuses),
        "human_escalations": sum(1 for status in statuses if status == HUMAN_CONTROLLED),
        "hot_leads": sum(1 for lead in latest_lead_by_conversation.values() if lead == HOT_LEAD),
        "intent_distribution": dict(Counter(point.intent for point in analyses)),
        "avg_response_ms": round(sum(measured) / len(measured)) if measured else None,
        "total_tokens": sum(point.token_usage for point in analyses),
        "messages_per_hour": buckets,
        "failed_jobs": failed_jobs,
    }
