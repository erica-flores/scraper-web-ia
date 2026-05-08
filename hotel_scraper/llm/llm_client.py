"""Public LLM facade. Delegates to LLMRouter; preserves the original API.

Module-level singletons (`_router`, `_cache`) ensure all callers share the
same config, cache and provider instances even when each instantiates
LLMClient on its own.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from loguru import logger

from llm.cache import LLMCache
from llm.router import LLMRouter
from llm.types import LLMResponse, TaskKind, load_router_config


_PROVIDERS_YAML = Path(__file__).parent / "providers.yaml"

_router: Optional[LLMRouter] = None
_cache: Optional[LLMCache] = None
_last_response: Optional[LLMResponse] = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _get_router() -> LLMRouter:
    """Lazy-init the singleton router + cache. Raises if providers.yaml is broken."""
    global _router, _cache
    if _router is not None:
        return _router

    config = load_router_config(_PROVIDERS_YAML)
    cache_enabled = config.cache.enabled and _env_bool("LLM_CACHE_ENABLED", True)
    _cache = LLMCache(
        db_path=Path(config.cache.db_path),
        ttl_hours=config.cache.ttl_hours,
        enabled=cache_enabled,
    )
    _router = LLMRouter(config, cache=_cache)
    logger.info(
        "[llm] router ready: chains={chains}, cache={cache}",
        chains=[t.value for t in config.chains],
        cache="on" if cache_enabled else "off",
    )
    return _router


def _strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` fences if a provider returned them despite json_mode."""
    raw = text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


class LLMClient:
    """Thin facade kept for backward compatibility with existing callers.

    The two public methods delegate to the shared LLMRouter:
    - extract_json:        TaskKind.EXTRACTION_LONG (HTML fragments up to ~18k chars)
    - extract_json_quick:  TaskKind.QUICK (link selection, selector discovery)
    - generate_text:       TaskKind.CHAT (free-form conversational replies)
    """

    def __init__(self) -> None:
        """Eagerly trigger router init to surface config errors at construction time."""
        _get_router()

    @property
    def last_response(self) -> Optional[LLMResponse]:
        """Metadata of the most recent successful call across the process."""
        return _last_response

    def extract_json(self, prompt: str) -> dict | list:
        """Run a long-context extraction and parse the JSON response."""
        return self._run_json(TaskKind.EXTRACTION_LONG, prompt)

    def extract_json_quick(self, prompt: str) -> dict | list:
        """Run a short-context structured task (link nav, selector discovery) and parse JSON."""
        return self._run_json(TaskKind.QUICK, prompt)

    def generate_text(self, prompt: str) -> str:
        """Run a free-form chat completion and return the raw text."""
        global _last_response
        response = _get_router().run(TaskKind.CHAT, prompt, json_mode=False)
        _last_response = response
        return response.text

    def _run_json(self, task: TaskKind, prompt: str) -> dict | list:
        global _last_response
        response = _get_router().run(task, prompt, json_mode=True)
        _last_response = response
        cleaned = _strip_json_fences(response.text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(
                "[llm] JSON parse failed for {prov}:{mdl}: {err}",
                prov=response.provider,
                mdl=response.model,
                err=str(e)[:200],
            )
            raise ValueError(f"LLM JSON parse failed: {e}") from e
