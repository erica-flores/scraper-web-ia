"""Tests for LLMCache: hits, TTL, disabled mode, hash separation by task."""

from __future__ import annotations

import time

from llm.cache import LLMCache, _hash
from llm.types import LLMResponse, TaskKind


def _resp(text: str = "ok", model: str = "m1") -> LLMResponse:
    return LLMResponse(text=text, provider="fake", model=model, latency_ms=42, cached=False)


def test_cache_hit_returns_response_with_cached_flag(tmp_path):
    db = tmp_path / "c.sqlite"
    cache = LLMCache(db_path=db, ttl_hours=1, enabled=True)

    cache.put(TaskKind.EXTRACTION_LONG, "the prompt", _resp(text="hello", model="m1"))
    hit = cache.get(TaskKind.EXTRACTION_LONG, "the prompt")

    assert hit is not None
    assert hit.text == "hello"
    assert hit.cached is True
    assert hit.provider == "fake"
    assert hit.model == "m1"
    assert hit.latency_ms == 42


def test_cache_miss_returns_none(tmp_path):
    db = tmp_path / "c.sqlite"
    cache = LLMCache(db_path=db, ttl_hours=1, enabled=True)

    assert cache.get(TaskKind.EXTRACTION_LONG, "never-stored") is None


def test_cache_ttl_expiration(tmp_path):
    """An entry older than ttl_hours must not be returned."""
    db = tmp_path / "c.sqlite"
    cache = LLMCache(db_path=db, ttl_hours=1, enabled=True)
    cache.put(TaskKind.EXTRACTION_LONG, "x", _resp())

    # Backdate the row 2h into the past via the cache's own connection
    cache._conn.execute(
        "UPDATE llm_cache SET created_at = ?",
        (int(time.time()) - 7200,),
    )
    cache._conn.commit()

    assert cache.get(TaskKind.EXTRACTION_LONG, "x") is None


def test_cache_disabled_bypasses_db(tmp_path):
    db = tmp_path / "should_not_be_created.sqlite"
    cache = LLMCache(db_path=db, ttl_hours=1, enabled=False)

    cache.put(TaskKind.EXTRACTION_LONG, "x", _resp())

    assert cache.get(TaskKind.EXTRACTION_LONG, "x") is None
    assert not db.exists()
    assert cache.enabled is False


def test_cache_clear_returns_deleted_count(tmp_path):
    db = tmp_path / "c.sqlite"
    cache = LLMCache(db_path=db, ttl_hours=1, enabled=True)
    cache.put(TaskKind.EXTRACTION_LONG, "a", _resp())
    cache.put(TaskKind.QUICK, "b", _resp())

    deleted = cache.clear()

    assert deleted == 2
    assert cache.get(TaskKind.EXTRACTION_LONG, "a") is None
    assert cache.get(TaskKind.QUICK, "b") is None


def test_hash_separates_tasks():
    """Same prompt under different tasks must produce different keys."""
    h1 = _hash(TaskKind.EXTRACTION_LONG, "same prompt")
    h2 = _hash(TaskKind.QUICK, "same prompt")
    h3 = _hash(TaskKind.CHAT, "same prompt")
    assert h1 != h2
    assert h1 != h3
    assert h2 != h3
