"""Pure aggregation behind the operator dashboard metrics (sec. 9 of the architecture)."""

from datetime import UTC, datetime, timedelta

from modules.analytics.service import AnalysisPoint, build_summary

NOW = datetime(2026, 10, 29, 12, 30, tzinfo=UTC)


def _summary(**overrides):
    base = {
        "statuses": [],
        "latest_lead_by_conversation": {},
        "analyses": [],
        "message_times": [],
        "failed_jobs": 0,
        "now": NOW,
    }
    base.update(overrides)
    return build_summary(**base)


def test_counts_active_and_human_controlled_conversations() -> None:
    summary = _summary(statuses=["AI_ACTIVE", "HUMAN_ACTIVE", "HUMAN_ACTIVE"])

    assert summary["active_conversations"] == 3
    assert summary["human_escalations"] == 2


def test_hot_leads_use_each_conversation_latest_status() -> None:
    summary = _summary(
        statuses=["AI_ACTIVE", "AI_ACTIVE"],
        latest_lead_by_conversation={"a": "LEAD_CALIENTE", "b": "DUDOSO"},
    )

    assert summary["hot_leads"] == 1


def test_intent_distribution_counts_each_intent() -> None:
    analyses = [
        AnalysisPoint(intent="ACADEMICO", latency_ms=100, token_usage=0),
        AnalysisPoint(intent="COMERCIAL", latency_ms=300, token_usage=0),
        AnalysisPoint(intent="ACADEMICO", latency_ms=0, token_usage=0),
    ]

    summary = _summary(analyses=analyses)

    assert summary["intent_distribution"] == {"ACADEMICO": 2, "COMERCIAL": 1}


def test_average_response_time_ignores_unmeasured_latency() -> None:
    analyses = [
        AnalysisPoint(intent="ACADEMICO", latency_ms=100, token_usage=0),
        AnalysisPoint(intent="ACADEMICO", latency_ms=300, token_usage=0),
        AnalysisPoint(intent="ACADEMICO", latency_ms=0, token_usage=0),
    ]

    assert _summary(analyses=analyses)["avg_response_ms"] == 200


def test_average_response_time_is_none_without_measurements() -> None:
    assert _summary(analyses=[])["avg_response_ms"] is None


def test_total_tokens_are_summed() -> None:
    analyses = [
        AnalysisPoint(intent="ACADEMICO", latency_ms=10, token_usage=120),
        AnalysisPoint(intent="COMERCIAL", latency_ms=10, token_usage=80),
    ]

    assert _summary(analyses=analyses)["total_tokens"] == 200


def test_messages_per_hour_has_24_buckets_ending_at_current_hour() -> None:
    times = [NOW - timedelta(minutes=5), NOW - timedelta(hours=1, minutes=30)]

    buckets = _summary(message_times=times)["messages_per_hour"]

    assert len(buckets) == 24
    assert buckets[-1] == {"hour": "2026-10-29T12:00:00", "count": 1}
    assert buckets[-2] == {"hour": "2026-10-29T11:00:00", "count": 1}


def test_messages_older_than_24_hours_are_excluded() -> None:
    times = [NOW - timedelta(hours=25)]

    buckets = _summary(message_times=times)["messages_per_hour"]

    assert sum(bucket["count"] for bucket in buckets) == 0


def test_failed_jobs_are_reported() -> None:
    assert _summary(failed_jobs=3)["failed_jobs"] == 3
