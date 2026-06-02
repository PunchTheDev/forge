"""
LLM client for Forge agents.

Reads configuration from environment:
  FORGE_LLM_KEY          — OpenRouter API key (required at chat time)
  FORGE_MODEL            — model ID to use (e.g. "anthropic/claude-haiku-4-5")
  FORGE_MODEL_WHITELIST  — comma-separated allowed model IDs; omit to allow any
"""

from __future__ import annotations

import os
from typing import Any

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMClient:
    def __init__(self) -> None:
        self._key = os.environ.get("FORGE_LLM_KEY", "").strip()
        self._model = os.environ.get("FORGE_MODEL", "").strip()

        raw_whitelist = os.environ.get("FORGE_MODEL_WHITELIST", "").strip()
        self._whitelist: list[str] | None = (
            [m.strip() for m in raw_whitelist.split(",") if m.strip()]
            if raw_whitelist
            else None
        )

        if self._whitelist is not None and self._model not in self._whitelist:
            raise ValueError(
                f"Model {self._model!r} is not in the whitelist: {self._whitelist}"
            )

    @property
    def model(self) -> str:
        return self._model

    def chat(self, messages: list[dict[str, Any]], max_tokens: int = 4096) -> str:
        if not self._key:
            raise RuntimeError("No LLM key configured — set FORGE_LLM_KEY")

        response = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "messages": messages,
                "max_tokens": max_tokens,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
