"""Gemini provider via the google-genai SDK."""

from __future__ import annotations

import time

from llm.providers.base import FatalError, LLMProvider, RetryableError
from llm.types import LLMResponse

_RETRYABLE_TOKENS = (
    "429",
    "503",
    "UNAVAILABLE",
    "RATE_LIMIT",
    "overloaded",
    "quota",
    "deadline",
    "timeout",
)

_FATAL_TOKENS = (
    "API_KEY_INVALID",
    "PERMISSION_DENIED",
    "INVALID_ARGUMENT",
    "401",
    "403",
)


class GeminiProvider(LLMProvider):
    """Wraps google-genai's generate_content for one specific model."""

    name = "gemini"

    def __init__(self, model_id: str, api_key: str, max_input_tokens: int) -> None:
        """Initialize the underlying genai client for this model.

        Args:
            model_id: Gemini model identifier (e.g. 'gemini-2.5-flash-lite').
            api_key: Google AI Studio API key.
            max_input_tokens: Upper bound this slot accepts in input tokens.
        """
        from google import genai

        self.model_id = model_id
        self.max_input_tokens = max_input_tokens
        self._client = genai.Client(api_key=api_key)

    def complete(self, prompt: str, *, json_mode: bool) -> LLMResponse:
        """Send one prompt to Gemini and return the raw text response."""
        from google.genai import types as genai_types

        config = None
        if json_mode:
            config = genai_types.GenerateContentConfig(
                response_mime_type="application/json"
            )

        start = time.perf_counter()
        try:
            response = self._client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=config,
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            raise _classify(e, self.model_id, elapsed_ms) from e

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        text = (response.text or "").strip()
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model_id,
            latency_ms=elapsed_ms,
            cached=False,
        )


def _classify(err: Exception, model: str, elapsed_ms: int) -> Exception:
    """Map a genai exception into RetryableError or FatalError."""
    msg = str(err)
    if any(tok in msg for tok in _FATAL_TOKENS):
        return FatalError(f"[gemini:{model}] fatal after {elapsed_ms}ms: {msg[:200]}")
    if any(tok in msg for tok in _RETRYABLE_TOKENS):
        return RetryableError(f"[gemini:{model}] retryable after {elapsed_ms}ms: {msg[:200]}")
    return RetryableError(f"[gemini:{model}] unknown after {elapsed_ms}ms: {msg[:200]}")
