"""Operator authentication for the dashboard REST API and WebSocket.

A single shared key (DASHBOARD_API_KEY) identifies the operator console. REST sends it in the
X-Operator-Key header; WebSocket sends it as ?token= because browsers cannot set headers on
WebSocket handshakes. The key is compared in constant time and never logged.
"""

from secrets import compare_digest
from typing import Annotated

from fastapi import Header, HTTPException, WebSocket, status

from shared.config.settings import get_settings


def _is_valid(provided: str | None) -> bool:
    expected = get_settings().dashboard_api_key
    if not expected or provided is None:
        return False
    return compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def require_operator(
    x_operator_key: Annotated[str | None, Header()] = None,
) -> None:
    """FastAPI dependency for every operator REST route."""
    if not get_settings().dashboard_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Operator API is not configured",
        )
    if not _is_valid(x_operator_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid operator key")


async def authorize_operator_websocket(websocket: WebSocket) -> bool:
    """Accept the connection only with a valid ?token=; otherwise close with policy violation."""
    if _is_valid(websocket.query_params.get("token")):
        return True
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    return False
