"""LLMRouter: walks a fallback chain per TaskKind, retrying transient errors per slot."""

from __future__ import annotations

import os
from typing import Optional

from loguru import logger
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from llm.cache import LLMCache
from llm.providers.base import (
    FatalError,
    LLMProvider,
    LLMProviderError,
    RetryableError,
)
from llm.providers.gemini import GeminiProvider
from llm.providers.openai_compatible import OpenAICompatibleProvider
from llm.types import LLMResponse, ProviderConfig, RouterConfig, TaskKind


def _estimate_input_tokens(prompt: str) -> int:
    """Rough heuristic: ~4 chars per token. Used to skip oversized slots."""
    return max(1, len(prompt) // 4)


class _SlotState:
    """Lazy holder for one ProviderConfig: caches the provider or the disabled reason."""

    def __init__(self, cfg: ProviderConfig) -> None:
        self.cfg = cfg
        self._provider: Optional[LLMProvider] = None
        self._disabled_reason: Optional[str] = None

    @property
    def disabled_reason(self) -> Optional[str]:
        return self._disabled_reason

    def resolve(self) -> Optional[LLMProvider]:
        """Instantiate the provider on first use. Returns None if env is missing."""
        if self._provider is not None:
            return self._provider
        if self._disabled_reason is not None:
            return None

        cfg = self.cfg
        api_key = os.getenv(cfg.api_key_env, "") if cfg.api_key_env else ""
        base_url = os.getenv(cfg.base_url_env, "") if cfg.base_url_env else ""

        try:
            if cfg.provider == "gemini":
                if not api_key:
                    self._disabled_reason = f"missing env {cfg.api_key_env}"
                    return None
                self._provider = GeminiProvider(
                    model_id=cfg.model,
                    api_key=api_key,
                    max_input_tokens=cfg.max_input_tokens,
                )
            elif cfg.provider == "openai_compatible":
                missing: list[str] = []
                if not api_key and cfg.api_key_env:
                    missing.append(cfg.api_key_env)
                if not base_url and cfg.base_url_env:
                    missing.append(cfg.base_url_env)
                if missing:
                    self._disabled_reason = f"missing env {', '.join(missing)}"
                    return None
                self._provider = OpenAICompatibleProvider(
                    model_id=cfg.model,
                    base_url=base_url,
                    api_key=api_key,
                    max_input_tokens=cfg.max_input_tokens,
                )
            else:
                self._disabled_reason = f"unknown provider type '{cfg.provider}'"
                return None
        except Exception as e:
            self._disabled_reason = f"init failed: {str(e)[:120]}"
            return None

        return self._provider


class LLMRouter:
    """Picks the chain for a TaskKind and runs it slot-by-slot until one succeeds."""

    def __init__(self, config: RouterConfig, cache: Optional[LLMCache] = None) -> None:
        self._config = config
        self._cache = cache
        self._slots: dict[TaskKind, list[_SlotState]] = {
            task: [_SlotState(cfg) for cfg in slots]
            for task, slots in config.chains.items()
        }

    def run(self, task: TaskKind, prompt: str, *, json_mode: bool) -> LLMResponse:
        """Walk the chain for `task` and return the first successful LLMResponse.

        Args:
            task: Logical task category (selects the chain).
            prompt: Fully formatted prompt.
            json_mode: Whether to request structured JSON output from the provider.

        Returns:
            LLMResponse from the first slot that succeeds.

        Raises:
            RuntimeError: If every slot is skipped or fails.
        """
        if self._cache is not None:
            cached = self._cache.get(task, prompt)
            if cached is not None:
                logger.bind(task=task.value, provider=cached.provider, model=cached.model).info(
                    "[llm] cache hit ({mdl})", mdl=cached.model
                )
                return cached

        chain = self._slots[task]
        estimated_tokens = _estimate_input_tokens(prompt)
        last_error: Optional[BaseException] = None

        for slot in chain:
            cfg = slot.cfg
            log = logger.bind(task=task.value, provider=cfg.provider, model=cfg.model)

            if estimated_tokens > cfg.max_input_tokens:
                log.info(
                    "[llm] skipped (oversized prompt {est} > cap {cap})",
                    est=estimated_tokens,
                    cap=cfg.max_input_tokens,
                )
                continue

            provider = slot.resolve()
            if provider is None:
                log.info("[llm] skipped ({reason})", reason=slot.disabled_reason)
                continue

            try:
                response = self._attempt(provider, prompt, json_mode)
                log.info(
                    "[llm] success ({ms}ms, model={mdl})",
                    ms=response.latency_ms,
                    mdl=response.model,
                )
                if self._cache is not None:
                    self._cache.put(task, prompt, response)
                return response
            except RetryError as retry_err:
                inner = retry_err.last_attempt.exception()
                last_error = inner
                log.warning("[llm] retry exhausted: {err}", err=str(inner)[:200])
            except FatalError as e:
                last_error = e
                log.warning("[llm] fatal: {err}", err=str(e)[:200])
            except LLMProviderError as e:
                last_error = e
                log.warning("[llm] provider error: {err}", err=str(e)[:200])

        raise RuntimeError(
            f"Todos los proveedores LLM fallaron para '{task.value}'. "
            f"Último error: {last_error}"
        )

    @retry(
        retry=retry_if_exception_type(RetryableError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def _attempt(
        self, provider: LLMProvider, prompt: str, json_mode: bool
    ) -> LLMResponse:
        """One provider call wrapped with backoff retry on RetryableError only."""
        return provider.complete(prompt, json_mode=json_mode)
