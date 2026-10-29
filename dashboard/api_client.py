"""HTTP client for the operator API. The dashboard talks only to FastAPI, never to Telegram.

The operator key lives in the client headers and is never rendered in the UI.
"""

from typing import Any

import httpx


class OperatorApiError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code


class OperatorApi:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    @classmethod
    def from_config(cls, base_url: str, operator_key: str, timeout: float = 10.0) -> "OperatorApi":
        return cls(
            httpx.Client(
                base_url=base_url.rstrip("/"),
                headers={"X-Operator-Key": operator_key},
                timeout=timeout,
            )
        )

    def list_conversations(self) -> list[dict[str, Any]]:
        return self._get("/api/conversations")

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self._get(f"/api/conversations/{conversation_id}")

    def messages(self, conversation_id: str) -> list[dict[str, Any]]:
        return self._get(f"/api/conversations/{conversation_id}/messages")

    def takeover(self, conversation_id: str) -> dict[str, Any]:
        return self._post(f"/api/conversations/{conversation_id}/takeover")

    def resume(self, conversation_id: str) -> dict[str, Any]:
        return self._post(f"/api/conversations/{conversation_id}/resume")

    def reply(self, conversation_id: str, text: str) -> dict[str, Any]:
        return self._post(f"/api/conversations/{conversation_id}/reply", json={"text": text})

    def summary(self) -> dict[str, Any]:
        return self._get("/api/analytics/summary")

    def _get(self, path: str) -> Any:
        return self._send(lambda: self._http.get(path))

    def _post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return self._send(lambda: self._http.post(path, json=json))

    def _send(self, call) -> Any:
        # Network failures become an operator error so the UI can show them instead of crashing.
        try:
            response = call()
        except httpx.HTTPError as error:
            raise OperatorApiError(503, f"API no disponible: {error}") from error
        return self._handle(response)

    @staticmethod
    def _handle(response: httpx.Response) -> Any:
        if response.status_code >= 400:
            try:
                detail = str(response.json().get("detail", response.text))
            except ValueError:
                detail = response.text
            raise OperatorApiError(response.status_code, detail)
        return response.json()
