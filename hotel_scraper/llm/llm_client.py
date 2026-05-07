"""Unified LLM client with retry logic and multi-model fallback chain."""

import json
import time
import random
from loguru import logger
from config import Config


class LLMClient:
    """Calls Gemini API with automatic retry and fallback across multiple models."""

    # Fallback chain: try each model in order until one works.
    # Uses confirmed available model names from the API.
    _MODEL_CHAIN = [
        "gemini-2.0-flash",       # Primary — fast and capable
        "gemini-2.5-flash-lite",  # Lighter, usually has more quota
        "gemini-2.0-flash-lite",  # Another lite option
        "gemini-2.5-flash",       # Full 2.5 — only if others fail
    ]

    def __init__(self) -> None:
        if not Config.GEMINI_API_KEY:
            raise RuntimeError(
                "No LLM API key configured. Set GEMINI_API_KEY in .env. "
                "Get a free key at https://aistudio.google.com/"
            )
        from google import genai
        self._client = genai.Client(api_key=Config.GEMINI_API_KEY)
        self._model_name = self._MODEL_CHAIN[0]
        logger.info(f"LLMClient: using {self._model_name} via google-genai")

    def extract_json(self, prompt: str) -> dict | list:
        """Send prompt to LLM and parse JSON response.

        Tries each model in the fallback chain with exponential backoff.

        Args:
            prompt: Fully formatted prompt string.

        Returns:
            Parsed Python dict or list from LLM JSON response.

        Raises:
            ValueError: If LLM returns invalid JSON (not retryable).
            RuntimeError: If all models are unavailable after retries.
        """
        for i, model in enumerate(self._MODEL_CHAIN):
            result = self._try_with_retry(prompt, model, max_retries=2)
            if result is not None:
                if model != self._MODEL_CHAIN[0]:
                    logger.info(f"Used fallback model: {model}")
                return result
            logger.warning(f"Model {model} unavailable, trying next in chain...")
            if i < len(self._MODEL_CHAIN) - 1:
                time.sleep(2)  # short pause before switching models


        raise RuntimeError(
            "Todos los modelos de Gemini están saturados. "
            "Esperá unos segundos y volvé a intentar."
        )

    def _try_with_retry(self, prompt: str, model: str, max_retries: int) -> dict | list | None:
        """Attempt one model with exponential backoff on 503/429.

        Returns:
            Parsed result on success.
            None if all retries fail with transient errors.

        Raises:
            ValueError: On JSON parse error (caller should not retry).
        """
        for attempt in range(max_retries):
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                raw = response.text.strip()

                # Strip markdown code fences if present
                if raw.startswith("```"):
                    parts = raw.split("```")
                    raw = parts[1] if len(parts) > 1 else raw
                    if raw.startswith("json"):
                        raw = raw[4:]
                raw = raw.strip()

                return json.loads(raw)

            except json.JSONDecodeError as e:
                logger.error(f"LLM returned invalid JSON (model={model}): {e}")
                raise ValueError(f"LLM JSON parse failed: {e}") from e

            except Exception as e:
                err_str = str(e)
                is_retryable = any(
                    tok in err_str
                    for tok in ("503", "429", "UNAVAILABLE", "RATE_LIMIT", "overloaded", "quota")
                )

                if is_retryable and attempt < max_retries - 1:
                    wait = (2 ** attempt) + random.uniform(0.5, 2.0)
                    logger.warning(
                        f"Gemini {model} busy (attempt {attempt + 1}/{max_retries}). "
                        f"Retrying in {wait:.1f}s..."
                    )
                    time.sleep(wait)
                else:
                    logger.warning(f"Gemini {model} failed: {err_str[:120]}")
                    return None

        return None

    def generate_text(self, prompt: str) -> str:
        """Generate free-form text (not JSON). Used by the chat endpoint.

        Same retry/fallback logic as extract_json.
        """
        for i, model in enumerate(self._MODEL_CHAIN):
            text = self._try_text_with_retry(prompt, model, max_retries=2)
            if text is not None:
                return text
            logger.warning(f"Model {model} unavailable for text gen, trying next...")
            if i < len(self._MODEL_CHAIN) - 1:
                time.sleep(2)


        raise RuntimeError(
            "Todos los modelos de Gemini están saturados. "
            "Esperá unos segundos y volvé a intentar."
        )

    def _try_text_with_retry(self, prompt: str, model: str, max_retries: int) -> str | None:
        """Like _try_with_retry but returns raw text instead of parsed JSON."""
        for attempt in range(max_retries):
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                return response.text.strip()

            except Exception as e:
                err_str = str(e)
                is_retryable = any(
                    tok in err_str
                    for tok in ("503", "429", "UNAVAILABLE", "RATE_LIMIT", "overloaded", "quota")
                )

                if is_retryable and attempt < max_retries - 1:
                    wait = (2 ** attempt) + random.uniform(0.5, 2.0)
                    logger.warning(
                        f"Gemini {model} busy for text (attempt {attempt + 1}/{max_retries}). "
                        f"Retrying in {wait:.1f}s..."
                    )
                    time.sleep(wait)
                else:
                    logger.warning(f"Gemini {model} text gen failed: {err_str[:120]}")
                    return None

        return None
