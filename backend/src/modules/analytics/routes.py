"""Operator-only metrics endpoint for the dashboard. Reads persisted rows only."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from modules.analytics.service import AnalysisPoint, build_summary
from modules.conversations.repository import ConversationRepository
from shared.database.session import get_db_session
from shared.security.operator_auth import require_operator

router = APIRouter(dependencies=[Depends(require_operator)])


@router.get("/summary")
def summary(session: Annotated[Session, Depends(get_db_session)]) -> dict[str, Any]:
    """Counts and distributions for the monitoring screen (sec. 9 of the architecture)."""
    repo = ConversationRepository(session)
    now = datetime.now(UTC)
    return build_summary(
        statuses=[conv.status for conv in repo.list_active_conversations()],
        latest_lead_by_conversation=repo.latest_leads_by_conversation(),
        analyses=[AnalysisPoint(*row) for row in repo.analysis_points()],
        message_times=repo.message_times_since(now - timedelta(hours=24)),
        failed_jobs=repo.failed_jobs_count(),
        now=now,
    )
