"""Cursor Cloud Agents adapter for the LLMClient port (fallback provider).

Cursor exposes no chat-completions endpoint, so each prompt runs as a cloud agent without
repositories: create agent -> poll its run -> read ``result`` -> delete the agent.
Every call consumes Cursor credits and takes seconds, so it is only used as a fallback.
"""

import time
from collections.abc import Callable
from typing import Any

import httpx

from modules.ai_engine.ports import LLMUnavailableError

CURSOR_API_URL = "https://api.cursor.com"
_OK_STATUS = "FINISHED"
_FAILED_STATUSES = frozenset({"ERROR", "CANCELLED", "EXPIRED"})
_UNAVAILABLE_CODES = frozenset({429, 503})


class CursorAgentClient:
    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        *,
        client: httpx.Client | None = None,
        poll_interval: float = 2.0,
        timeout: float = 120.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if client is None and not api_key:
            raise ValueError("CURSOR_API_KEY is not set")
        self._http = client or httpx.Client(
            base_url=CURSOR_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        self._model = model
        self._poll_interval = poll_interval
        self._timeout = timeout
        self._sleep = sleep

    def generate(self, prompt: str) -> str:
        body: dict[str, Any] = {"prompt": {"text": prompt}}
        if self._model:
            body["model"] = {"id": self._model}

        created = self._request("POST", "/v1/agents", json=body)
        agent_id = created["agent"]["id"]
        run_id = created["run"]["id"]
        try:
            run = self._wait_for_run(agent_id, run_id)
        finally:
            self._delete_agent(agent_id)

        text = str(run.get("result") or "").strip()
        if not text:
            raise RuntimeError("Cursor agent returned an empty result")
        return text

    def _wait_for_run(self, agent_id: str, run_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self._timeout
        while True:
            run = self._request("GET", f"/v1/agents/{agent_id}/runs/{run_id}")
            status = run.get("status")
            if status == _OK_STATUS:
                return run
            if status in _FAILED_STATUSES:
                raise RuntimeError(f"Cursor run ended with status {status}")
            if time.monotonic() >= deadline:
                raise LLMUnavailableError("Cursor agent run timed out")
            self._sleep(self._poll_interval)

    def _delete_agent(self, agent_id: str) -> None:
        try:
            self._request("DELETE", f"/v1/agents/{agent_id}")
        except (RuntimeError, LLMUnavailableError, httpx.HTTPError):
            # Cleanup is best effort; the answer already exists.
            pass

    def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            response = self._http.request(method, path, json=json)
        except httpx.TransportError as error:
            raise LLMUnavailableError(f"Cursor unreachable: {error}") from error
        if response.status_code in _UNAVAILABLE_CODES:
            raise LLMUnavailableError(f"Cursor unavailable ({response.status_code})")
        if response.status_code >= 400:
            raise RuntimeError(f"Cursor API error {response.status_code}: {response.text[:200]}")
        return response.json()
