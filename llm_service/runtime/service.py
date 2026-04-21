from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from string import Template

import aiosqlite

from llm_service.config import LLMServiceConfig
from llm_service.providers.base import ProviderProtocol
from llm_service.runtime.event_bus import EventBus
from llm_service.runtime.executor import Executor
from llm_service.runtime.task_manager import TaskManager
from llm_service.runtime.template_registry import TemplateRegistry


class LLMService:
    """Top-level orchestrator: owns task_manager, executor, event_bus, provider, templates."""

    def __init__(
        self,
        db: aiosqlite.Connection,
        provider: ProviderProtocol,
        config: LLMServiceConfig,
    ):
        self._db = db
        self._config = config
        self._bus = EventBus(db)
        self._mgr = TaskManager(
            db, self._bus,
            max_attempts=config.default_max_attempts,
            lease_duration=config.lease_duration,
            backoff_base=config.retry_backoff_base,
            backoff_max=config.retry_backoff_max,
        )
        self._executor = Executor(db, self._mgr, self._bus, provider)
        self._templates = TemplateRegistry(db)

    # ------------------------------------------------------------------
    # Template resolution
    # ------------------------------------------------------------------

    async def _resolve_template(
        self,
        template_key: str | None,
        input: dict | None,
        messages: list[dict] | None,
        expected_output_type: str,
        output_schema: dict | None,
    ) -> dict:
        """If template_key is given, expand template into messages/schema.

        Caller-provided messages/schema take precedence over template defaults.
        """
        result = {
            "messages": messages,
            "expected_output_type": expected_output_type,
            "output_schema": output_schema,
        }
        if not template_key:
            return result

        tpl = await self._templates.get_by_key(template_key)
        if not tpl:
            return result

        # Build messages from template if caller didn't provide them
        if not messages:
            msgs = []
            if tpl.get("system_prompt"):
                msgs.append({"role": "system", "content": tpl["system_prompt"]})
            user_content = tpl.get("user_prompt_template", "")
            if input:
                # Use safe_substitute to avoid injection via str.format
                tmpl = Template(user_content)
                user_content = tmpl.safe_substitute(input)
            msgs.append({"role": "user", "content": user_content})
            result["messages"] = msgs

        # Template schema/type as fallback
        if not output_schema and tpl.get("output_schema_json"):
            try:
                result["output_schema"] = json.loads(tpl["output_schema_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        return result

    # ------------------------------------------------------------------
    # Submit (async)
    # ------------------------------------------------------------------

    async def submit(
        self,
        caller_domain: str,
        pipeline_stage: str,
        *,
        template_key: str | None = None,
        input: dict | None = None,
        messages: list[dict] | None = None,
        params: dict | None = None,
        expected_output_type: str = "json_object",
        output_schema: dict | None = None,
        ref_type: str | None = None,
        ref_id: str | None = None,
        build_id: str | None = None,
        release_id: str | None = None,
        request_id: str | None = None,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
        priority: int = 100,
    ) -> str:
        # Template expansion
        resolved = await self._resolve_template(
            template_key, input, messages, expected_output_type, output_schema,
        )
        actual_messages = resolved["messages"]
        actual_expected_type = resolved["expected_output_type"]
        actual_schema = resolved["output_schema"]

        task_id = await self._mgr.submit(
            caller_domain, pipeline_stage,
            request_id=request_id,
            idempotency_key=idempotency_key,
            ref_type=ref_type, ref_id=ref_id,
            build_id=build_id, release_id=release_id,
            max_attempts=max_attempts, priority=priority,
        )

        # Only create request row if this is a new task
        cur = await self._db.execute("SELECT COUNT(*) as cnt FROM agent_llm_requests WHERE task_id = ?", (task_id,))
        req_count = (await cur.fetchone())["cnt"]
        if req_count == 0:
            now = datetime.now(timezone.utc).isoformat()
            actual_request_id = request_id or str(uuid.uuid4())
            provider_instance = self._executor._provider
            await self._db.execute(
                """INSERT INTO agent_llm_requests
                   (id, task_id, provider, model, prompt_template_key, messages_json, input_json,
                    params_json, expected_output_type, output_schema_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    actual_request_id, task_id, provider_instance.provider_name,
                    provider_instance.default_model, template_key,
                    json.dumps(actual_messages or []), json.dumps(input or {}),
                    json.dumps(params or {}), actual_expected_type,
                    json.dumps(actual_schema or {}), now,
                ),
            )
            await self._db.commit()

        return task_id

    # ------------------------------------------------------------------
    # Execute (sync)
    # ------------------------------------------------------------------

    async def execute(
        self,
        caller_domain: str,
        pipeline_stage: str,
        *,
        template_key: str | None = None,
        input: dict | None = None,
        messages: list[dict] | None = None,
        params: dict | None = None,
        expected_output_type: str = "json_object",
        output_schema: dict | None = None,
        ref_type: str | None = None,
        ref_id: str | None = None,
        build_id: str | None = None,
        release_id: str | None = None,
        request_id: str | None = None,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
        priority: int = 100,
        timeout: int | None = None,
    ) -> dict:
        """Sync execute: submit, then run immediately, return result."""
        task_id = await self.submit(
            caller_domain, pipeline_stage,
            template_key=template_key, input=input, messages=messages,
            params=params, expected_output_type=expected_output_type,
            output_schema=output_schema,
            ref_type=ref_type, ref_id=ref_id,
            build_id=build_id, release_id=release_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            max_attempts=max_attempts, priority=priority,
        )

        # Idempotency: already-succeeded task → return cached result
        cur = await self._db.execute("SELECT status FROM agent_llm_tasks WHERE id = ?", (task_id,))
        row = await cur.fetchone()
        if row["status"] == "succeeded":
            return await self._build_execute_response(task_id)

        # Resolve messages for execution (template may have expanded them)
        resolved = await self._resolve_template(
            template_key, input, messages, expected_output_type, output_schema,
        )
        actual_messages = resolved["messages"] or [{"role": "user", "content": json.dumps(input or {})}]
        actual_expected_type = resolved["expected_output_type"]
        actual_schema = resolved["output_schema"]

        # Directly set to running and execute (sync path, no queue)
        now_iso = datetime.now(timezone.utc).isoformat()
        lease_dt = datetime.now(timezone.utc) + timedelta(seconds=self._config.lease_duration)
        await self._db.execute(
            "UPDATE agent_llm_tasks SET status = 'running', started_at = ?, lease_expires_at = ?, updated_at = ? WHERE id = ?",
            (now_iso, lease_dt.isoformat(), now_iso, task_id),
        )
        await self._db.commit()

        effective_timeout = timeout or self._config.execute_timeout
        try:
            await asyncio.wait_for(
                self._executor.run(
                    task_id, actual_messages, params or {},
                    expected_type=actual_expected_type, schema=actual_schema,
                ),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            # Per design: timeout does NOT fail the task.
            # Task stays 'running'; lease recovery will handle it later.
            await self._bus.emit(task_id, "failed", f"execute timed out after {effective_timeout}s (lease recovery pending)")
            return await self._build_execute_response(task_id)

        return await self._build_execute_response(task_id)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    async def _build_execute_response(self, task_id: str) -> dict:
        cur = await self._db.execute("SELECT status, attempt_count FROM agent_llm_tasks WHERE id = ?", (task_id,))
        task = await cur.fetchone()
        if not task:
            return {"task_id": task_id, "status": "unknown", "attempts": 0, "result": None, "error": None}

        cur = await self._db.execute("SELECT parse_status, parsed_output_json, text_output, validation_errors_json FROM agent_llm_results WHERE task_id = ?", (task_id,))
        result_row = await cur.fetchone()

        cur = await self._db.execute("SELECT total_tokens, latency_ms FROM agent_llm_attempts WHERE task_id = ? ORDER BY attempt_no DESC LIMIT 1", (task_id,))
        attempt_row = await cur.fetchone()

        resp = {
            "task_id": task_id,
            "status": task["status"],
            "attempts": task["attempt_count"],
            "total_tokens": attempt_row["total_tokens"] if attempt_row else None,
            "latency_ms": attempt_row["latency_ms"] if attempt_row else None,
        }

        if result_row:
            parsed = json.loads(result_row["parsed_output_json"]) if result_row["parsed_output_json"] else None
            validation = json.loads(result_row["validation_errors_json"]) if result_row["validation_errors_json"] else []
            resp["result"] = {
                "parse_status": result_row["parse_status"],
                "parsed_output": parsed if parsed != {} else None,
                "text_output": result_row["text_output"],
                "validation_errors": validation,
            }
        else:
            resp["result"] = None

        if task["status"] in ("dead_letter", "failed"):
            cur = await self._db.execute("SELECT error_type, error_message FROM agent_llm_attempts WHERE task_id = ? AND status = 'failed' ORDER BY attempt_no DESC LIMIT 1", (task_id,))
            err_row = await cur.fetchone()
            resp["error"] = {
                "error_type": err_row["error_type"] if err_row else None,
                "error_message": err_row["error_message"] if err_row else None,
            }
        else:
            resp["error"] = None

        return resp

    async def get_task(self, task_id: str) -> dict | None:
        cur = await self._db.execute("SELECT * FROM agent_llm_tasks WHERE id = ?", (task_id,))
        row = await cur.fetchone()
        if not row:
            return None
        return dict(row)

    async def cancel(self, task_id: str) -> None:
        await self._mgr.cancel(task_id)

    async def get_result(self, task_id: str) -> dict | None:
        cur = await self._db.execute("SELECT * FROM agent_llm_results WHERE task_id = ?", (task_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_attempts(self, task_id: str) -> list[dict]:
        cur = await self._db.execute("SELECT * FROM agent_llm_attempts WHERE task_id = ? ORDER BY attempt_no", (task_id,))
        return [dict(r) for r in await cur.fetchall()]

    async def get_events(self, task_id: str) -> list[dict]:
        cur = await self._db.execute("SELECT * FROM agent_llm_events WHERE task_id = ? ORDER BY created_at", (task_id,))
        return [dict(r) for r in await cur.fetchall()]
