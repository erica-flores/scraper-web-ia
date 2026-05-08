"""Shared types for the LLM layer: task kinds, provider config, response envelope."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, model_validator


class TaskKind(str, Enum):
    """Logical task category. Selects which fallback chain the router uses."""

    EXTRACTION_LONG = "extraction_long"
    QUICK = "quick"
    CHAT = "chat"


class ProviderConfig(BaseModel):
    """One slot inside a fallback chain."""

    provider: str
    model: str
    base_url_env: Optional[str] = None
    api_key_env: Optional[str] = None
    max_input_tokens: int = Field(gt=0)


class CacheConfig(BaseModel):
    enabled: bool = True
    db_path: str = ".cache/llm_cache.sqlite"
    ttl_hours: int = Field(default=24, gt=0)


class RouterConfig(BaseModel):
    """Full LLM layer configuration loaded from providers.yaml."""

    cache: CacheConfig = CacheConfig()
    chains: dict[TaskKind, list[ProviderConfig]]

    @model_validator(mode="after")
    def _all_tasks_have_at_least_one_slot(self) -> "RouterConfig":
        for task in TaskKind:
            slots = self.chains.get(task)
            if not slots:
                raise ValueError(f"Chain for task '{task.value}' is empty or missing")
        return self


class LLMResponse(BaseModel):
    """Envelope returned by every provider call."""

    text: str
    provider: str
    model: str
    latency_ms: int
    cached: bool = False


def load_router_config(yaml_path: Path) -> RouterConfig:
    """Read providers.yaml and validate it as a RouterConfig.

    Args:
        yaml_path: Absolute path to providers.yaml.

    Returns:
        Validated RouterConfig instance.

    Raises:
        FileNotFoundError: If yaml_path does not exist.
        pydantic.ValidationError: If the YAML structure is invalid.
    """
    with yaml_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return RouterConfig.model_validate(raw)
