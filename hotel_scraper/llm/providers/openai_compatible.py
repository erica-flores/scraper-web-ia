"""Provider for any backend that exposes an OpenAI-compatible /chat/completions API.

Covers Groq, Cerebras and OpenRouter with the same code path. The friendly
provider name is derived from the base_url so logs and metadata stay informative.
"""

from __future__ import annotations

import time
from urllib.parse import urlparse

from llm.providers.base import FatalError, LLMProvider, RetryableError
from llm.types import LLMResponse


_KNOWN_HOSTS = {
    "api.groq.com": "groq",
    "api.cerebras.ai": "cerebras",
    "openrouter.ai": "openrouter",
}


def _friendly_name(base_url: str) -> str:
    """Derive a short provider name from the host (e.g. 'groq', 'cerebras')."""
    host = urlparse(base_url).netloc
    if host in _KNOWN_HOSTS:
        return _KNOWN_HOSTS[host]
    return host or "openai_compatible"


class OpenAICompatibleProvider(LLMProvider):
    """One slot backed by an OpenAI-compatible endpoint."""

    def __init__(
        self,
        model_id: str,
        base_url: str,
        api_key: str,
        max_input_tokens: int,
    ) -> None:
        """Build the openai client for the given endpoint.

        Args:
            model_id: Model identifier accepted by this backend.
            base_url: Full base URL ending in /v1 (e.g. https://api.groq.com/openai/v1).
            api_key: API key for this backend.
            max_input_tokens: Upper bound this slot accepts in input tokens.
        """
        from openai import OpenAI

        self.model_id = model_id
        self.max_input_tokens = max_input_tokens
        self.name = _friendly_name(base_url)
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def complete(self, prompt: str, *, json_mode: bool) -> LLMResponse:
        """Send one prompt and return the raw text response."""
        from openai import (
            APIConnectionError,
            APIError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            BadRequestError,
            InternalServerError,
            PermissionDeniedError,
            RateLimitError,
        )

        kwargs: dict = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": prompt}],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        start = time.perf_counter()
        try:
            completion = self._client.chat.completions.create(**kwargs)
        except (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError) as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            raise RetryableError(
                f"[{self.name}:{self.model_id}] retryable after {elapsed_ms}ms: {str(e)[:200]}"
            ) from e
        except (AuthenticationError, PermissionDeniedError, BadRequestError) as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            raise FatalError(
                f"[{self.name}:{self.model_id}] fatal after {elapsed_ms}ms: {str(e)[:200]}"
            ) from e
        except APIStatusError as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            status = getattr(e, "status_code", 0) or 0
            if status in (429, 502, 503, 504) or 500 <= status < 600:
                raise RetryableError(
                    f"[{self.name}:{self.model_id}] retryable HTTP {status} after {elapsed_ms}ms"
                ) from e
            raise FatalError(
                f"[{self.name}:{self.model_id}] fatal HTTP {status} after {elapsed_ms}ms: {str(e)[:200]}"
            ) from e
        except APIError as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            raise RetryableError(
                f"[{self.name}:{self.model_id}] api error after {elapsed_ms}ms: {str(e)[:200]}"
            ) from e

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        text = (completion.choices[0].message.content or "").strip()
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model_id,
            latency_ms=elapsed_ms,
            cached=False,
        )
