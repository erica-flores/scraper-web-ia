"""SQLite-backed cache for LLM responses, keyed by (task, prompt) hash."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from loguru import logger

from llm.types import LLMResponse, TaskKind


_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_cache (
    prompt_hash TEXT PRIMARY KEY,
    task        TEXT NOT NULL,
    text        TEXT NOT NULL,
    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,
    latency_ms  INTEGER NOT NULL,
    created_at  INTEGER NOT NULL
)
"""


def _hash(task: TaskKind, prompt: str) -> str:
    """SHA-256 over `task|prompt` — collisions are astronomically improbable."""
    payload = f"{task.value}|{prompt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class LLMCache:
    """Thread-safe cache. When `enabled=False`, all operations are no-ops."""

    def __init__(self, db_path: Path, ttl_hours: int, enabled: bool = True) -> None:
        """Open (or lazily create) the SQLite DB at db_path."""
        self.enabled = enabled
        self._ttl_seconds = ttl_hours * 3600
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

        if not enabled:
            return

        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.execute(_SCHEMA)
            self._conn.commit()
        except sqlite3.Error as e:
            logger.warning(f"[llm.cache] init failed, disabling cache: {e}")
            self.enabled = False
            self._conn = None

    def get(self, task: TaskKind, prompt: str) -> Optional[LLMResponse]:
        """Return a cached response if present and not expired, else None."""
        if not self.enabled or self._conn is None:
            return None

        key = _hash(task, prompt)
        cutoff = int(time.time()) - self._ttl_seconds

        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT text, provider, model, latency_ms, created_at "
                    "FROM llm_cache WHERE prompt_hash = ?",
                    (key,),
                ).fetchone()
        except sqlite3.Error as e:
            logger.warning(f"[llm.cache] get failed: {e}")
            return None

        if row is None:
            return None

        text, provider, model, latency_ms, created_at = row
        if created_at < cutoff:
            return None

        return LLMResponse(
            text=text,
            provider=provider,
            model=model,
            latency_ms=latency_ms,
            cached=True,
        )

    def put(self, task: TaskKind, prompt: str, response: LLMResponse) -> None:
        """Store the response under hash(task, prompt). Silently no-op if disabled."""
        if not self.enabled or self._conn is None:
            return

        key = _hash(task, prompt)
        now = int(time.time())

        try:
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO llm_cache "
                    "(prompt_hash, task, text, provider, model, latency_ms, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        key,
                        task.value,
                        response.text,
                        response.provider,
                        response.model,
                        response.latency_ms,
                        now,
                    ),
                )
                self._conn.commit()
        except sqlite3.Error as e:
            logger.warning(f"[llm.cache] put failed: {e}")

    def clear(self) -> int:
        """Delete every cache row. Returns the count deleted (0 if disabled)."""
        if not self.enabled or self._conn is None:
            return 0
        with self._lock:
            cur = self._conn.execute("DELETE FROM llm_cache")
            self._conn.commit()
            return cur.rowcount or 0
