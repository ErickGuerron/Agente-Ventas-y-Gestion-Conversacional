"""MiniMax adapter for the LLMClient port (OpenAI-compatible chat completions).

Uses the cheapest, fastest setting for the bot: low reasoning effort and reasoning kept out of
the reply text. Only this module knows the MiniMax wire format.
"""

from typing import Any

import httpx

from modules.ai_engine.ports import LLMUnavailableError

MINIMAX_API_URL = "https://api.minimax.io"
_UNAVAILABLE_CODES = frozenset({429, 503})


class MinimaxClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        client: httpx.Client | None = None,
        timeout: float = 60.0,
    ) -> None:
        if client is None and not api_key:
            raise ValueError("MINIMAX_API_KEY is not set")
        self._http = client or httpx.Client(
            base_url=MINIMAX_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        self._model = model

    def generate(self, prompt: str) -> str:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "reasoning_effort": "low",
            "reasoning_split": True,
        }
        try:
            response = self._http.post("/v1/chat/completions", json=body)
        except httpx.TransportError as error:
            raise LLMUnavailableError(f"MiniMax unreachable: {error}") from error
        if response.status_code in _UNAVAILABLE_CODES:
            raise LLMUnavailableError(f"MiniMax unavailable ({response.status_code})")
        if response.status_code >= 400:
            raise RuntimeError(f"MiniMax API error {response.status_code}: {response.text[:200]}")

        text = str(response.json()["choices"][0]["message"].get("content") or "").strip()
        if not text:
            raise RuntimeError("MiniMax returned an empty response")
        return text
