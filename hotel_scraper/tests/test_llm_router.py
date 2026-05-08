"""Tests for LLMRouter fallback chain behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from llm.providers.base import FatalError, LLMProvider, RetryableError
from llm.router import LLMRouter, _SlotState
from llm.types import (
    CacheConfig,
    LLMResponse,
    ProviderConfig,
    RouterConfig,
    TaskKind,
    load_router_config,
)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Make tenacity's exponential backoff instant so tests don't actually wait."""
    monkeypatch.setattr("time.sleep", lambda *a, **kw: None)


class FakeProvider(LLMProvider):
    """Provider whose behavior is scripted by a list of items.

    Each item is either an Exception (raised) or an LLMResponse (returned).
    """

    name = "fake"

    def __init__(self, model_id: str, max_input_tokens: int = 100_000, script=None) -> None:
        self.model_id = model_id
        self.max_input_tokens = max_input_tokens
        self.script = list(script or [])
        self.call_count = 0

    def complete(self, prompt: str, *, json_mode: bool) -> LLMResponse:
        self.call_count += 1
        if not self.script:
            raise RuntimeError(f"FakeProvider {self.model_id} script exhausted")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _ok(model: str = "fake", text: str = "ok") -> LLMResponse:
    return LLMResponse(text=text, provider="fake", model=model, latency_ms=10, cached=False)


def _make_router(*fakes: FakeProvider, task: TaskKind = TaskKind.EXTRACTION_LONG) -> LLMRouter:
    """Build an LLMRouter where the chosen task's chain uses the given fakes pre-resolved."""
    placeholder_chains = {
        t: [ProviderConfig(provider="gemini", model="placeholder",
                           api_key_env="UNUSED", max_input_tokens=10_000)]
        for t in TaskKind
    }
    config = RouterConfig(cache=CacheConfig(enabled=False), chains=placeholder_chains)
    router = LLMRouter(config, cache=None)

    new_slots: list[_SlotState] = []
    for fake in fakes:
        cfg = ProviderConfig(
            provider="gemini",
            model=fake.model_id,
            api_key_env="UNUSED",
            max_input_tokens=fake.max_input_tokens,
        )
        slot = _SlotState(cfg)
        slot._provider = fake  # bypass real resolve()
        new_slots.append(slot)
    router._slots[task] = new_slots
    return router


# --- Tests --------------------------------------------------------------------


def test_chain_falls_back_on_retryable_error():
    """tenacity exhausts 3 attempts on slot 1, router moves to slot 2."""
    p1 = FakeProvider(
        "primary",
        script=[RetryableError("HTTP 429"), RetryableError("HTTP 429"), RetryableError("HTTP 429")],
    )
    p2 = FakeProvider("secondary", script=[_ok(model="secondary", text='{"ok": 1}')])
    router = _make_router(p1, p2)

    response = router.run(TaskKind.EXTRACTION_LONG, "test prompt", json_mode=True)

    assert response.model == "secondary"
    assert response.text == '{"ok": 1}'
    assert p1.call_count == 3
    assert p2.call_count == 1


def test_chain_falls_back_on_fatal_without_retry():
    """FatalError moves to next slot immediately (no retry)."""
    p1 = FakeProvider("primary", script=[FatalError("invalid api key")])
    p2 = FakeProvider("secondary", script=[_ok(model="secondary")])
    router = _make_router(p1, p2)

    response = router.run(TaskKind.EXTRACTION_LONG, "test", json_mode=True)

    assert response.model == "secondary"
    assert p1.call_count == 1  # not retried
    assert p2.call_count == 1


def test_chain_skips_disabled_provider(monkeypatch):
    """A slot whose api_key_env is missing in the environment is skipped."""
    monkeypatch.delenv("UNSET_KEY_FOR_TEST", raising=False)

    cfg_disabled = ProviderConfig(
        provider="gemini", model="primary",
        api_key_env="UNSET_KEY_FOR_TEST", max_input_tokens=10_000,
    )
    slot_disabled = _SlotState(cfg_disabled)  # _provider stays None → resolve will check env

    p2 = FakeProvider("secondary", script=[_ok(model="secondary")])
    cfg2 = ProviderConfig(
        provider="gemini", model="secondary",
        api_key_env="UNUSED", max_input_tokens=10_000,
    )
    slot2 = _SlotState(cfg2)
    slot2._provider = p2

    placeholder_chains = {
        t: [cfg_disabled, cfg2] for t in TaskKind
    }
    config = RouterConfig(cache=CacheConfig(enabled=False), chains=placeholder_chains)
    router = LLMRouter(config, cache=None)
    router._slots[TaskKind.EXTRACTION_LONG] = [slot_disabled, slot2]

    response = router.run(TaskKind.EXTRACTION_LONG, "test", json_mode=True)

    assert response.model == "secondary"
    assert slot_disabled.disabled_reason is not None
    assert "UNSET_KEY_FOR_TEST" in slot_disabled.disabled_reason
    assert p2.call_count == 1


def test_chain_skips_oversized_prompt():
    """A slot whose max_input_tokens is below the estimated prompt tokens is skipped."""
    p1_small = FakeProvider("small", max_input_tokens=10, script=[])
    p2_large = FakeProvider("large", max_input_tokens=100_000, script=[_ok(model="large")])
    router = _make_router(p1_small, p2_large)

    long_prompt = "x" * 1000  # ~250 estimated tokens, > 10

    response = router.run(TaskKind.EXTRACTION_LONG, long_prompt, json_mode=True)

    assert response.model == "large"
    assert p1_small.call_count == 0  # never called: skipped before resolve
    assert p2_large.call_count == 1


def test_chain_all_fail_raises():
    """When every slot fails, router raises RuntimeError with a clear message."""
    p1 = FakeProvider("p1", script=[FatalError("auth")])
    p2 = FakeProvider("p2", script=[FatalError("auth")])
    router = _make_router(p1, p2)

    with pytest.raises(RuntimeError, match="Todos los proveedores LLM fallaron"):
        router.run(TaskKind.EXTRACTION_LONG, "test", json_mode=True)

    assert p1.call_count == 1
    assert p2.call_count == 1


def test_no_retired_models_in_default_config():
    """Regression for the original incident: gemini-2.0-flash retired 2026-03-03.

    The shipped providers.yaml must not list any deprecated/retired Gemini variants
    in any active chain.
    """
    yaml_path = Path(__file__).parent.parent / "llm" / "providers.yaml"
    config = load_router_config(yaml_path)

    forbidden = {"gemini-2.0-flash", "gemini-2.0-flash-lite"}
    for task, slots in config.chains.items():
        for slot in slots:
            assert slot.model not in forbidden, (
                f"Retired model '{slot.model}' present in chain '{task.value}'"
            )
