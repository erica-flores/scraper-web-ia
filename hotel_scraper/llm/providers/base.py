"""Provider contract: every LLM backend implements LLMProvider.complete()."""

from __future__ import annotations

from abc import ABC, abstractmethod

from llm.types import LLMResponse


class LLMProviderError(Exception):
    """Base class for all provider errors raised through the contract."""


class RetryableError(LLMProviderError):
    """Transient error: 429/503/timeout/connection. Router may retry or fall back."""


class FatalError(LLMProviderError):
    """Permanent error for this slot: 4xx auth, malformed prompt, schema rejection."""


class LLMProvider(ABC):
    """Single backend slot in a fallback chain."""

    name: str
    model_id: str
    max_input_tokens: int

    @abstractmethod
    def complete(self, prompt: str, *, json_mode: bool) -> LLMResponse:
        """Run one completion against this backend.

        Args:
            prompt: Fully formatted prompt string.
            json_mode: If True, request structured JSON output (provider-specific flag).

        Returns:
            LLMResponse with raw text plus provider/model/latency metadata.

        Raises:
            RetryableError: Transient failure; router may retry or move to next slot.
            FatalError: Permanent failure for this slot; router moves to next slot.
        """
