"""Gemini adapter for the LLMClient port. The only module that imports the Google SDK."""

from typing import Any

from google import genai
from google.genai import errors as genai_errors

from modules.ai_engine.ports import LLMUnavailableError

_UNAVAILABLE_CODES = frozenset({429, 503})


class GeminiClient:
    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        if client is None and not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        self._client = client if client is not None else genai.Client(api_key=api_key)
        self._model = model

    def generate(self, prompt: str) -> str:
        try:
            response = self._client.models.generate_content(model=self._model, contents=prompt)
        except genai_errors.APIError as error:
            if error.code in _UNAVAILABLE_CODES:
                raise LLMUnavailableError(f"Gemini unavailable ({error.code})") from error
            raise
        text = response.text
        if not text:
            raise RuntimeError("Gemini returned an empty response")
        return text
