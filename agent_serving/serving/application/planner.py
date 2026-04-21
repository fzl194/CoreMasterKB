"""LLM Runtime client — thin wrapper over agent_llm_runtime DB.

Serving calls LLM through this client for query understanding.
All audit and logging goes to agent_llm_runtime, not Serving's own tables.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class LLMRuntimeClient:
    """Client for LLM calls via agent_llm_runtime database."""

    def __init__(self, db: aiosqlite.Connection | None = None) -> None:
        self._db = db

    async def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        model: str = "default",
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> str:
        """Call LLM and log to agent_llm_runtime.

        For v1.1, this is a placeholder that returns empty string.
        Real implementation requires agent_llm_runtime service.
        """
        # v1.1: placeholder — will be connected to actual LLM service
        logger.info("LLM complete called (placeholder): model=%s", model)
        return ""

    def is_available(self) -> bool:
        """Check if LLM runtime is available."""
        return self._db is not None
