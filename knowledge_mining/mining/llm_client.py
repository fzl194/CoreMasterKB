"""Independent HTTP client for llm_service — Mining does not import llm_service package.

Supports:
- submit_task: POST /api/v1/tasks (async batch)
- poll_result: GET /api/v1/tasks/{id}/result
- register_template: POST /api/v1/templates (idempotent)

All methods return None on failure (non-blocking for pipeline).
"""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)


class LlmClient:
    """HTTP client for llm_service. Uses stdlib urllib (no external deps)."""

    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 30) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def submit_task(
        self,
        template_key: str,
        variables: dict[str, str],
        caller_domain: str = "mining",
        pipeline_stage: str = "retrieval_units",
    ) -> str | None:
        """Submit an async task. Returns task_id or None on failure."""
        try:
            payload = json.dumps({
                "template_key": template_key,
                "template_version": "1",
                "variables": variables,
                "caller_domain": caller_domain,
                "pipeline_stage": pipeline_stage,
            }).encode("utf-8")

            req = Request(
                f"{self._base_url}/api/v1/tasks",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("task_id") or data.get("id")
        except Exception as e:
            logger.debug("submit_task failed: %s", e)
            return None

    def poll_result(self, task_id: str, timeout: int = 30) -> str | None:
        """Poll task result. Returns result text or None."""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                req = Request(
                    f"{self._base_url}/api/v1/tasks/{task_id}/result",
                    method="GET",
                )
                with urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    status = data.get("status", "")
                    if status == "succeeded":
                        return data.get("result", "")
                    if status in ("failed", "cancelled"):
                        return None
                    # pending/running — wait and retry
                    time.sleep(1)
            except Exception as e:
                logger.debug("poll_result failed: %s", e)
                return None
        return None

    def register_template(self, template: dict[str, Any]) -> bool:
        """Idempotent template registration. Returns True on success."""
        try:
            payload = json.dumps(template).encode("utf-8")
            req = Request(
                f"{self._base_url}/api/v1/templates",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=self._timeout) as resp:
                return resp.status in (200, 201)
        except Exception as e:
            logger.debug("register_template failed: %s", e)
            return False
