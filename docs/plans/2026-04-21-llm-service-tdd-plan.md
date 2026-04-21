# LLM Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an independent FastAPI service that provides unified LLM call + audit capabilities for Mining and Serving.

**Architecture:** Single-process FastAPI with asyncio background workers. SQLite (WAL mode) stores task/request/attempt/result/event chain. One execution engine shared by async `/tasks` and sync `/execute` endpoints. Jinja2+HTMX dashboard for monitoring.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, aiosqlite, httpx, Jinja2, HTMX, jsonschema

**Design doc:** `docs/plans/2026-04-21-v11-llm-service-impl-plan.md`
**DB schema:** `databases/agent_llm_runtime/schemas/001_agent_llm_runtime.sqlite.sql`
**Git prefix:** `[claude-llm]`

---

## Phase 1: Skeleton & Core Chain

### Task 1: Project Skeleton

**Files:**
- Create: `llm_service/__init__.py`
- Create: `llm_service/config.py`
- Create: `llm_service/db.py`
- Create: `llm_service/main.py`
- Modify: `pyproject.toml`

**Step 1: Write the failing test**

Create `llm_service/tests/__init__.py` and `llm_service/tests/conftest.py`:

```python
# llm_service/tests/conftest.py
import os
import pytest
import aiosqlite

# Ensure test mode
os.environ["LLM_SERVICE_DB_PATH"] = ""  # will use temp


@pytest.fixture
async def db(tmp_path):
    """Create a fresh test database with schema initialized."""
    db_path = str(tmp_path / "test_llm.sqlite")
    from llm_service.db import init_db
    conn = await init_db(db_path)
    yield conn
    await conn.close()


@pytest.fixture
def config(tmp_path):
    from llm_service.config import LLMServiceConfig
    return LLMServiceConfig(
        db_path=str(tmp_path / "test_llm.sqlite"),
        provider_base_url="http://localhost:11434/v1",
        provider_api_key="test-key",
        provider_model="test-model",
    )
```

Create `llm_service/tests/test_skeleton.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_db_init_creates_all_tables(db):
    """All 6 agent_llm_* tables must exist after init."""
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'agent_llm_%' ORDER BY name"
    )
    tables = [row[0] for row in await cursor.fetchall()]
    expected = [
        "agent_llm_attempts",
        "agent_llm_events",
        "agent_llm_prompt_templates",
        "agent_llm_requests",
        "agent_llm_results",
        "agent_llm_tasks",
    ]
    assert tables == expected


async def test_config_defaults():
    from llm_service.config import LLMServiceConfig

    cfg = LLMServiceConfig()
    assert cfg.port == 8900
    assert cfg.default_max_attempts == 3
    assert cfg.retry_backoff_base == 2.0


async def test_fastapi_app_creates():
    from llm_service.main import create_app

    app = create_app()
    assert app.title == "LLM Service"
```

**Step 2: Run test to verify it fails**

Run: `cd D:/mywork/KnowledgeBase/CoreMasterKB && python -m pytest llm_service/tests/test_skeleton.py -v`
Expected: FAIL — module `llm_service` not found

**Step 3: Write minimal implementation**

```python
# llm_service/__init__.py
"""LLM Service — unified LLM call and audit runtime."""
```

```python
# llm_service/config.py
from pydantic_settings import BaseSettings
from pydantic import Field


class LLMServiceConfig(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8900

    db_path: str = "data/llm_service.sqlite"

    provider_base_url: str = "https://api.openai.com/v1"
    provider_api_key: str = ""
    provider_model: str = "gpt-4o"
    provider_headers: dict = Field(default_factory=dict)
    provider_timeout: int = 30

    worker_concurrency: int = 4
    default_max_attempts: int = 3
    retry_backoff_base: float = 2.0
    retry_backoff_max: float = 60.0

    execute_timeout: int = 60
    lease_duration: int = 300

    model_config = {"env_prefix": "LLM_SERVICE_"}
```

```python
# llm_service/db.py
from pathlib import Path

import aiosqlite

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "databases" / "agent_llm_runtime" / "schemas" / "001_agent_llm_runtime.sqlite.sql"


async def init_db(db_path: str) -> aiosqlite.Connection:
    """Open (or create) the SQLite database and ensure schema is applied."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute("PRAGMA journal_mode = WAL")
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    await conn.executescript(schema_sql)
    await conn.commit()
    return conn
```

```python
# llm_service/main.py
from fastapi import FastAPI

from llm_service.config import LLMServiceConfig


def create_app(config: LLMServiceConfig | None = None) -> FastAPI:
    cfg = config or LLMServiceConfig()
    app = FastAPI(title="LLM Service", version="0.1.0")
    app.state.config = cfg
    return app
```

Update `pyproject.toml` — add `llm_service*` to packages.find.include and add `jinja2`, `jsonschema` dependencies:

```toml
[tool.setuptools.packages.find]
include = ["agent_serving*", "knowledge_mining*", "llm_service*"]
```

Add to dependencies:
```
    "jinja2>=3.1",
    "jsonschema>=4.21",
```

**Step 4: Run test to verify it passes**

Run: `cd D:/mywork/KnowledgeBase/CoreMasterKB && python -m pytest llm_service/tests/test_skeleton.py -v`
Expected: 3 PASS

**Step 5: Commit**

```bash
git add llm_service/ pyproject.toml
git commit -m "[claude-llm]: T1 scaffold llm_service with config/db/main"
```

---

### Task 2: Pydantic Models

**Files:**
- Create: `llm_service/models.py`
- Test: `llm_service/tests/test_models.py`

**Step 1: Write the failing test**

```python
# llm_service/tests/test_models.py
import pytest
from llm_service.models import (
    TaskSubmitRequest,
    TaskSubmitResponse,
    ExecuteResponse,
    ParsedResult,
    ErrorInfo,
)


def test_task_submit_request_defaults():
    req = TaskSubmitRequest(
        caller_domain="mining",
        pipeline_stage="summary_generation",
    )
    assert req.caller_domain == "mining"
    assert req.max_attempts == 3
    assert req.priority == 100
    assert req.params is None
    assert req.idempotency_key is None


def test_task_submit_request_validation_rejects_bad_domain():
    with pytest.raises(ValueError):
        TaskSubmitRequest(
            caller_domain="invalid_domain",
            pipeline_stage="test",
        )


def test_execute_response_with_result():
    resp = ExecuteResponse(
        task_id="t-1",
        status="succeeded",
        result=ParsedResult(
            parse_status="succeeded",
            parsed_output={"summary": "hello"},
        ),
        attempts=1,
        total_tokens=100,
        latency_ms=500,
        error=None,
    )
    assert resp.result.parse_status == "succeeded"
    assert resp.result.parsed_output["summary"] == "hello"


def test_execute_response_with_error():
    resp = ExecuteResponse(
        task_id="t-1",
        status="failed",
        result=None,
        attempts=3,
        total_tokens=300,
        latency_ms=1500,
        error=ErrorInfo(
            error_type="provider_error",
            error_message="timeout after 30s",
        ),
    )
    assert resp.error.error_type == "provider_error"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest llm_service/tests/test_models.py -v`
Expected: FAIL — import error

**Step 3: Write minimal implementation**

```python
# llm_service/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


# --- Request models ---

class TaskSubmitRequest(BaseModel):
    caller_domain: str = Field(..., pattern="^(mining|serving|evaluation|admin)$")
    pipeline_stage: str
    template_key: str | None = None
    input: dict[str, Any] | None = None
    messages: list[dict[str, Any]] | None = None
    params: dict[str, Any] | None = None
    expected_output_type: str = Field(default="json_object", pattern="^(json_object|json_array|text)$")
    output_schema: dict[str, Any] | None = None
    ref_type: str | None = None
    ref_id: str | None = None
    build_id: str | None = None
    release_id: str | None = None
    idempotency_key: str | None = None
    max_attempts: int = Field(default=3, ge=1, le=10)
    priority: int = Field(default=100, ge=1)


# --- Response dataclasses ---

@dataclass
class ParsedResult:
    parse_status: str  # succeeded | failed | schema_invalid
    parsed_output: dict | list | None = None
    text_output: str | None = None
    confidence: float | None = None
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class ErrorInfo:
    error_type: str
    error_message: str


@dataclass
class TaskSubmitResponse:
    task_id: str
    status: str
    idempotency_key: str | None
    created_at: str


@dataclass
class ExecuteResponse:
    task_id: str
    status: str  # succeeded | failed | timeout
    result: ParsedResult | None
    attempts: int
    total_tokens: int | None
    latency_ms: int | None
    error: ErrorInfo | None


@dataclass
class TaskDetail:
    task_id: str
    caller_domain: str
    pipeline_stage: str
    status: str
    ref_type: str | None
    ref_id: str | None
    build_id: str | None
    release_id: str | None
    attempt_count: int
    max_attempts: int
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None


@dataclass
class AttemptDetail:
    attempt_id: str
    attempt_no: int
    status: str
    error_type: str | None
    error_message: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    latency_ms: int | None
    started_at: str
    finished_at: str | None
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest llm_service/tests/test_models.py -v`
Expected: 4 PASS

**Step 5: Commit**

```bash
git add llm_service/models.py llm_service/tests/test_models.py
git commit -m "[claude-llm]: T2 add Pydantic request/response models"
```

---

### Task 3: Provider Layer (Protocol + Mock + OpenAI-compatible)

**Files:**
- Create: `llm_service/providers/__init__.py`
- Create: `llm_service/providers/base.py`
- Create: `llm_service/providers/mock.py`
- Create: `llm_service/providers/openai_compatible.py`
- Test: `llm_service/tests/test_providers.py`

**Step 1: Write the failing test**

```python
# llm_service/tests/test_providers.py
import pytest

pytestmark = pytest.mark.asyncio


async def test_mock_provider_returns_preset_response():
    from llm_service.providers.mock import MockProvider

    provider = MockProvider(
        responses=[{"choices": [{"message": {"content": '{"answer": 42}'}}]}]
    )
    resp = await provider.complete(
        messages=[{"role": "user", "content": "test"}],
        params={},
    )
    assert resp.output_text == '{"answer": 42}'
    assert resp.provider_name == "mock"


async def test_mock_provider_cycles_responses():
    from llm_service.providers.mock import MockProvider

    provider = MockProvider(
        responses=[
            {"choices": [{"message": {"content": "first"}}]},
            {"choices": [{"message": {"content": "second"}}]},
        ]
    )
    r1 = await provider.complete(messages=[], params={})
    r2 = await provider.complete(messages=[], params={})
    assert r1.output_text == "first"
    assert r2.output_text == "second"


async def test_mock_provider_can_raise_error():
    from llm_service.providers.mock import MockProvider
    from llm_service.providers.base import ProviderError

    provider = MockProvider(error=ProviderError("timeout", "connection timed out"))
    with pytest.raises(ProviderError):
        await provider.complete(messages=[], params={})


async def test_openai_compatible_builds_correct_url():
    from llm_service.providers.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        base_url="http://localhost:11434/v1",
        api_key="test-key",
        model="llama3",
    )
    assert provider.provider_name == "openai_compatible"
    assert provider.default_model == "llama3"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest llm_service/tests/test_providers.py -v`
Expected: FAIL — import error

**Step 3: Write minimal implementation**

```python
# llm_service/providers/__init__.py
```

```python
# llm_service/providers/base.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class ProviderResponse:
    output_text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    provider_request_id: str | None = None
    raw_response: dict | None = None


class ProviderError(Exception):
    def __init__(self, error_type: str, message: str):
        self.error_type = error_type
        self.message = message
        super().__init__(message)


@runtime_checkable
class ProviderProtocol(Protocol):
    async def complete(
        self,
        messages: list[dict],
        params: dict,
    ) -> ProviderResponse: ...

    @property
    def provider_name(self) -> str: ...

    @property
    def default_model(self) -> str: ...
```

```python
# llm_service/providers/mock.py
from __future__ import annotations

from llm_service.providers.base import ProviderError, ProviderResponse


class MockProvider:
    def __init__(
        self,
        responses: list[dict] | None = None,
        error: ProviderError | None = None,
    ):
        self._responses = responses or []
        self._index = 0
        self._error = error

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def default_model(self) -> str:
        return "mock-model"

    async def complete(
        self,
        messages: list[dict],
        params: dict,
    ) -> ProviderResponse:
        if self._error:
            raise self._error
        if not self._responses:
            return ProviderResponse(output_text="")
        resp = self._responses[self._index % len(self._responses)]
        self._index += 1
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = resp.get("usage", {})
        return ProviderResponse(
            output_text=content,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            raw_response=resp,
        )
```

```python
# llm_service/providers/openai_compatible.py
from __future__ import annotations

import httpx

from llm_service.providers.base import ProviderError, ProviderResponse


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        headers: dict | None = None,
        timeout: int = 30,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._extra_headers = headers or {}
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        return "openai_compatible"

    @property
    def default_model(self) -> str:
        return self._model

    async def complete(
        self,
        messages: list[dict],
        params: dict,
    ) -> ProviderResponse:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }
        body = {
            "model": self._model,
            "messages": messages,
            **params,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.post(url, json=body, headers=headers)
            except httpx.TimeoutException as e:
                raise ProviderError("timeout", str(e)) from e
            except httpx.ConnectError as e:
                raise ProviderError("connection_error", str(e)) from e

        if resp.status_code == 429:
            raise ProviderError("rate_limited", resp.text)
        if resp.status_code >= 500:
            raise ProviderError("server_error", f"HTTP {resp.status_code}: {resp.text}")
        if resp.status_code >= 400:
            raise ProviderError("client_error", f"HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        return ProviderResponse(
            output_text=content,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            provider_request_id=data.get("id"),
            raw_response=data,
        )
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest llm_service/tests/test_providers.py -v`
Expected: 4 PASS

**Step 5: Commit**

```bash
git add llm_service/providers/
git commit -m "[claude-llm]: T3 add provider layer with mock and openai-compatible"
```

---

### Task 4: Event Bus

**Files:**
- Create: `llm_service/runtime/__init__.py`
- Create: `llm_service/runtime/event_bus.py`
- Test: `llm_service/tests/test_event_bus.py`

**Step 1: Write the failing test**

```python
# llm_service/tests/test_event_bus.py
import pytest

pytestmark = pytest.mark.asyncio


async def test_emit_creates_event_row(db):
    from llm_service.runtime.event_bus import EventBus

    bus = EventBus(db)
    # First create a task row so FK works
    await db.execute(
        "INSERT INTO agent_llm_tasks (id, caller_domain, pipeline_stage, status, priority, attempt_count, max_attempts, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("t-1", "mining", "test", "queued", 100, 0, 3, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    )
    await db.commit()

    event_id = await bus.emit(task_id="t-1", event_type="submitted", message="task submitted")
    assert event_id is not None

    cursor = await db.execute("SELECT event_type, message FROM agent_llm_events WHERE id = ?", (event_id,))
    row = await cursor.fetchone()
    assert row["event_type"] == "submitted"
    assert row["message"] == "task submitted"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest llm_service/tests/test_event_bus.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# llm_service/runtime/__init__.py
```

```python
# llm_service/runtime/event_bus.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite


class EventBus:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def emit(
        self,
        task_id: str,
        event_type: str,
        message: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        import json

        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO agent_llm_events (id, task_id, event_type, message, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, task_id, event_type, message, json.dumps(metadata or {}), now),
        )
        await self._db.commit()
        return event_id
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest llm_service/tests/test_event_bus.py -v`
Expected: 1 PASS

**Step 5: Commit**

```bash
git add llm_service/runtime/
git commit -m "[claude-llm]: T4 add event bus for agent_llm_events"
```

---

### Task 5: Task Manager

**Files:**
- Create: `llm_service/runtime/task_manager.py`
- Create: `llm_service/runtime/idempotency.py`
- Test: `llm_service/tests/test_task_manager.py`

**Step 1: Write the failing test**

```python
# llm_service/tests/test_task_manager.py
import pytest

pytestmark = pytest.mark.asyncio


async def test_submit_creates_task(db):
    from llm_service.runtime.task_manager import TaskManager
    from llm_service.runtime.event_bus import EventBus

    bus = EventBus(db)
    mgr = TaskManager(db, bus)
    task_id = await mgr.submit(
        caller_domain="mining",
        pipeline_stage="summary_generation",
    )
    assert task_id is not None

    cur = await db.execute("SELECT status, caller_domain, pipeline_stage FROM agent_llm_tasks WHERE id = ?", (task_id,))
    row = await cur.fetchone()
    assert row["status"] == "queued"
    assert row["caller_domain"] == "mining"


async def test_submit_with_idempotency_key(db):
    from llm_service.runtime.task_manager import TaskManager
    from llm_service.runtime.event_bus import EventBus

    bus = EventBus(db)
    mgr = TaskManager(db, bus)
    t1 = await mgr.submit(caller_domain="mining", pipeline_stage="test", idempotency_key="key-1")
    t2 = await mgr.submit(caller_domain="mining", pipeline_stage="test", idempotency_key="key-1")
    # Same key, both queued → should return same task
    assert t1 == t2


async def test_claim_picks_queued_task(db):
    from llm_service.runtime.task_manager import TaskManager
    from llm_service.runtime.event_bus import EventBus

    bus = EventBus(db)
    mgr = TaskManager(db, bus)
    task_id = await mgr.submit(caller_domain="mining", pipeline_stage="test")

    claimed = await mgr.claim()
    assert claimed == task_id

    cur = await db.execute("SELECT status FROM agent_llm_tasks WHERE id = ?", (task_id,))
    row = await cur.fetchone()
    assert row["status"] == "running"


async def test_claim_returns_none_when_empty(db):
    from llm_service.runtime.task_manager import TaskManager
    from llm_service.runtime.event_bus import EventBus

    bus = EventBus(db)
    mgr = TaskManager(db, bus)
    result = await mgr.claim()
    assert result is None


async def test_complete_transitions_task(db):
    from llm_service.runtime.task_manager import TaskManager
    from llm_service.runtime.event_bus import EventBus

    bus = EventBus(db)
    mgr = TaskManager(db, bus)
    task_id = await mgr.submit(caller_domain="mining", pipeline_stage="test")
    await mgr.claim()
    await mgr.complete(task_id)

    cur = await db.execute("SELECT status, finished_at FROM agent_llm_tasks WHERE id = ?", (task_id,))
    row = await cur.fetchone()
    assert row["status"] == "succeeded"
    assert row["finished_at"] is not None


async def test_fail_with_retry_marks_queued(db):
    from llm_service.runtime.task_manager import TaskManager
    from llm_service.runtime.event_bus import EventBus

    bus = EventBus(db)
    mgr = TaskManager(db, bus)
    task_id = await mgr.submit(caller_domain="mining", pipeline_stage="test", max_attempts=3)
    await mgr.claim()
    await mgr.fail(task_id, error_type="timeout", error_message="timed out")

    cur = await db.execute("SELECT status, attempt_count, available_at FROM agent_llm_tasks WHERE id = ?", (task_id,))
    row = await cur.fetchone()
    assert row["status"] == "queued"  # retry allowed
    assert row["attempt_count"] == 1
    assert row["available_at"] is not None


async def test_fail_exhausted_marks_dead_letter(db):
    from llm_service.runtime.task_manager import TaskManager
    from llm_service.runtime.event_bus import EventBus

    bus = EventBus(db)
    mgr = TaskManager(db, bus)
    task_id = await mgr.submit(caller_domain="mining", pipeline_stage="test", max_attempts=1)
    await mgr.claim()
    await mgr.fail(task_id, error_type="timeout", error_message="timed out")

    cur = await db.execute("SELECT status FROM agent_llm_tasks WHERE id = ?", (task_id,))
    row = await cur.fetchone()
    assert row["status"] == "dead_letter"


async def test_cancel(db):
    from llm_service.runtime.task_manager import TaskManager
    from llm_service.runtime.event_bus import EventBus

    bus = EventBus(db)
    mgr = TaskManager(db, bus)
    task_id = await mgr.submit(caller_domain="mining", pipeline_stage="test")
    await mgr.cancel(task_id)

    cur = await db.execute("SELECT status FROM agent_llm_tasks WHERE id = ?", (task_id,))
    row = await cur.fetchone()
    assert row["status"] == "cancelled"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest llm_service/tests/test_task_manager.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# llm_service/runtime/idempotency.py
from __future__ import annotations

import aiosqlite


async def find_existing_task(
    db: aiosqlite.Connection,
    idempotency_key: str,
) -> str | None:
    """Return task_id if a succeeded or running task exists for this key."""
    # Priority 1: latest succeeded
    cur = await db.execute(
        "SELECT id FROM agent_llm_tasks WHERE idempotency_key = ? AND status = 'succeeded' ORDER BY created_at DESC LIMIT 1",
        (idempotency_key,),
    )
    row = await cur.fetchone()
    if row:
        return row["id"]
    # Priority 2: latest running
    cur = await db.execute(
        "SELECT id FROM agent_llm_tasks WHERE idempotency_key = ? AND status = 'running' ORDER BY created_at DESC LIMIT 1",
        (idempotency_key,),
    )
    row = await cur.fetchone()
    if row:
        return row["id"]
    # Priority 3: allow new
    return None
```

```python
# llm_service/runtime/task_manager.py
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import aiosqlite

from llm_service.runtime.event_bus import EventBus
from llm_service.runtime.idempotency import find_existing_task


class TaskManager:
    def __init__(self, db: aiosqlite.Connection, event_bus: EventBus, max_attempts: int = 3, lease_duration: int = 300, backoff_base: float = 2.0, backoff_max: float = 60.0):
        self._db = db
        self._bus = event_bus
        self._default_max_attempts = max_attempts
        self._lease_duration = lease_duration
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max

    async def submit(
        self,
        caller_domain: str,
        pipeline_stage: str,
        *,
        idempotency_key: str | None = None,
        ref_type: str | None = None,
        ref_id: str | None = None,
        build_id: str | None = None,
        release_id: str | None = None,
        max_attempts: int | None = None,
        priority: int = 100,
        metadata: dict | None = None,
    ) -> str:
        # Idempotency check
        if idempotency_key:
            existing = await find_existing_task(self._db, idempotency_key)
            if existing:
                return existing

        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        ma = max_attempts or self._default_max_attempts
        await self._db.execute(
            """INSERT INTO agent_llm_tasks
               (id, caller_domain, pipeline_stage, ref_type, ref_id, build_id, release_id,
                idempotency_key, status, priority, available_at, attempt_count, max_attempts,
                created_at, updated_at, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, 0, ?, ?, ?, ?)""",
            (task_id, caller_domain, pipeline_stage, ref_type, ref_id, build_id, release_id,
             idempotency_key, priority, now, ma, now, now, json.dumps(metadata or {})),
        )
        await self._db.commit()
        await self._bus.emit(task_id, "submitted", "task submitted")
        return task_id

    async def claim(self) -> str | None:
        now = datetime.now(timezone.utc).isoformat()
        lease = datetime.now(timezone.utc).timestamp() + self._lease_duration
        lease_str = datetime.fromtimestamp(lease, tz=timezone.utc).isoformat()
        cur = await self._db.execute(
            """SELECT id FROM agent_llm_tasks
               WHERE status = 'queued' AND available_at <= ?
               ORDER BY priority DESC, created_at ASC LIMIT 1""",
            (now,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        task_id = row["id"]
        await self._db.execute(
            """UPDATE agent_llm_tasks
               SET status = 'running', started_at = ?, lease_expires_at = ?, updated_at = ?
               WHERE id = ?""",
            (now, lease_str, now, task_id),
        )
        await self._db.commit()
        await self._bus.emit(task_id, "claimed", "task claimed by worker")
        return task_id

    async def complete(self, task_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "UPDATE agent_llm_tasks SET status = 'succeeded', finished_at = ?, updated_at = ? WHERE id = ?",
            (now, now, task_id),
        )
        await self._db.execute(
            "UPDATE agent_llm_tasks SET attempt_count = attempt_count + 1 WHERE id = ?",
            (task_id,),
        )
        await self._db.commit()
        await self._bus.emit(task_id, "succeeded", "task completed")

    async def fail(self, task_id: str, error_type: str, error_message: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        # Read current state
        cur = await self._db.execute(
            "SELECT attempt_count, max_attempts FROM agent_llm_tasks WHERE id = ?",
            (task_id,),
        )
        row = await cur.fetchone()
        new_count = row["attempt_count"] + 1
        if new_count < row["max_attempts"]:
            # Retry: back to queued with backoff
            import math
            backoff = min(self._backoff_base ** new_count, self._backoff_max)
            from datetime import timedelta
            available = datetime.now(timezone.utc) + timedelta(seconds=backoff)
            await self._db.execute(
                """UPDATE agent_llm_tasks
                   SET status = 'queued', attempt_count = ?, available_at = ?, updated_at = ?
                   WHERE id = ?""",
                (new_count, available.isoformat(), now, task_id),
            )
            await self._db.commit()
            await self._bus.emit(task_id, "retried", f"attempt {new_count} failed: {error_message}")
        else:
            # Exhausted
            await self._db.execute(
                """UPDATE agent_llm_tasks
                   SET status = 'dead_letter', attempt_count = ?, finished_at = ?, updated_at = ?
                   WHERE id = ?""",
                (new_count, now, now, task_id),
            )
            await self._db.commit()
            await self._bus.emit(task_id, "dead_letter", f"exhausted after {new_count} attempts: {error_message}")

    async def cancel(self, task_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "UPDATE agent_llm_tasks SET status = 'cancelled', finished_at = ?, updated_at = ? WHERE id = ?",
            (now, now, task_id),
        )
        await self._db.commit()
        await self._bus.emit(task_id, "cancelled", "task cancelled")
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest llm_service/tests/test_task_manager.py -v`
Expected: 8 PASS

**Step 5: Commit**

```bash
git add llm_service/runtime/task_manager.py llm_service/runtime/idempotency.py llm_service/tests/test_task_manager.py
git commit -m "[claude-llm]: T5 add task manager with idempotency and claim logic"
```

---

### Task 6: Parser (Output Parse + Schema Validation)

**Files:**
- Create: `llm_service/runtime/parser.py`
- Test: `llm_service/tests/test_parser.py`

**Step 1: Write the failing test**

```python
# llm_service/tests/test_parser.py
import pytest
from llm_service.runtime.parser import parse_output


def test_parse_json_object_success():
    result = parse_output('{"answer": 42}', expected_type="json_object")
    assert result.parse_status == "succeeded"
    assert result.parsed_output == {"answer": 42}


def test_parse_json_array_success():
    result = parse_output('[1, 2, 3]', expected_type="json_array")
    assert result.parse_status == "succeeded"
    assert result.parsed_output == [1, 2, 3]


def test_parse_text_success():
    result = parse_output("hello world", expected_type="text")
    assert result.parse_status == "succeeded"
    assert result.text_output == "hello world"


def test_parse_json_failure():
    result = parse_output("not json", expected_type="json_object")
    assert result.parse_status == "failed"
    assert result.parse_error is not None


def test_schema_validation_pass():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
    result = parse_output('{"name": "test"}', expected_type="json_object", schema=schema)
    assert result.parse_status == "succeeded"


def test_schema_validation_fail():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
    result = parse_output('{"age": 10}', expected_type="json_object", schema=schema)
    assert result.parse_status == "schema_invalid"
    assert len(result.validation_errors) > 0


def test_text_type_skips_schema():
    result = parse_output("hello", expected_type="text", schema={"type": "string"})
    assert result.parse_status == "succeeded"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest llm_service/tests/test_parser.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# llm_service/runtime/parser.py
from __future__ import annotations

import json
from dataclasses import dataclass, field

from jsonschema import validate as js_validate, ValidationError as JsValidationError


@dataclass
class ParseResult:
    parse_status: str  # succeeded | failed | schema_invalid
    parsed_output: dict | list | None = None
    text_output: str | None = None
    parse_error: str | None = None
    validation_errors: list[str] = field(default_factory=list)


def parse_output(
    raw_text: str,
    expected_type: str,
    schema: dict | None = None,
) -> ParseResult:
    # Step 1: parse raw text
    if expected_type == "text":
        return ParseResult(parse_status="succeeded", text_output=raw_text)

    try:
        parsed = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as e:
        return ParseResult(parse_status="failed", parse_error=str(e))

    # Type check
    if expected_type == "json_object" and not isinstance(parsed, dict):
        return ParseResult(parse_status="failed", parse_error=f"expected json_object, got {type(parsed).__name__}")
    if expected_type == "json_array" and not isinstance(parsed, list):
        return ParseResult(parse_status="failed", parse_error=f"expected json_array, got {type(parsed).__name__}")

    # Step 2: schema validation
    if schema:
        try:
            js_validate(instance=parsed, schema=schema)
        except JsValidationError as e:
            return ParseResult(
                parse_status="schema_invalid",
                parsed_output=parsed,
                validation_errors=[e.message],
            )

    return ParseResult(parse_status="succeeded", parsed_output=parsed)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest llm_service/tests/test_parser.py -v`
Expected: 7 PASS

**Step 5: Commit**

```bash
git add llm_service/runtime/parser.py llm_service/tests/test_parser.py
git commit -m "[claude-llm]: T6 add output parser with JSON schema validation"
```

---

### Task 7: Executor (Provider Call + Attempt + Retry)

**Files:**
- Create: `llm_service/runtime/executor.py`
- Test: `llm_service/tests/test_executor.py`

**Step 1: Write the failing test**

```python
# llm_service/tests/test_executor.py
import pytest

pytestmark = pytest.mark.asyncio


async def test_execute_success(db):
    from llm_service.runtime.event_bus import EventBus
    from llm_service.runtime.task_manager import TaskManager
    from llm_service.runtime.executor import Executor
    from llm_service.providers.mock import MockProvider

    bus = EventBus(db)
    mgr = TaskManager(db, bus)
    provider = MockProvider(responses=[{"choices": [{"message": {"content": '{"summary": "ok"}'}}]}])
    executor = Executor(db, mgr, bus, provider)

    task_id = await mgr.submit(caller_domain="mining", pipeline_stage="test")
    result = await executor.run(task_id, messages=[{"role": "user", "content": "test"}], params={})

    assert result.parse_status == "succeeded"
    assert result.parsed_output == {"summary": "ok"}

    # Verify attempt recorded
    cur = await db.execute("SELECT status, latency_ms FROM agent_llm_attempts WHERE task_id = ?", (task_id,))
    row = await cur.fetchone()
    assert row["status"] == "succeeded"
    assert row["latency_ms"] is not None


async def test_execute_retries_on_failure(db):
    from llm_service.runtime.event_bus import EventBus
    from llm_service.runtime.task_manager import TaskManager
    from llm_service.runtime.executor import Executor
    from llm_service.providers.mock import MockProvider
    from llm_service.providers.base import ProviderError

    bus = EventBus(db)
    mgr = TaskManager(db, bus)
    # Fail first, succeed second
    provider = MockProvider(
        responses=[
            {"choices": [{"message": {"content": '{"answer": 42}'}}]},
        ]
    )
    # Force first call to fail
    call_count = 0
    original_complete = provider.complete

    async def flaky_complete(messages, params):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ProviderError("timeout", "first call timed out")
        return await original_complete(messages, params)

    provider.complete = flaky_complete
    executor = Executor(db, mgr, bus, provider)

    task_id = await mgr.submit(caller_domain="mining", pipeline_stage="test", max_attempts=3)
    result = await executor.run(task_id, messages=[{"role": "user", "content": "test"}], params={})

    assert result.parse_status == "succeeded"

    # Verify 2 attempts
    cur = await db.execute("SELECT COUNT(*) as cnt FROM agent_llm_attempts WHERE task_id = ?", (task_id,))
    row = await cur.fetchone()
    assert row["cnt"] == 2


async def test_execute_exhausted(db):
    from llm_service.runtime.event_bus import EventBus
    from llm_service.runtime.task_manager import TaskManager
    from llm_service.runtime.executor import Executor
    from llm_service.providers.mock import MockProvider
    from llm_service.providers.base import ProviderError

    bus = EventBus(db)
    mgr = TaskManager(db, bus)
    provider = MockProvider(error=ProviderError("timeout", "always fails"))
    executor = Executor(db, mgr, bus, provider)

    task_id = await mgr.submit(caller_domain="mining", pipeline_stage="test", max_attempts=2)
    result = await executor.run(task_id, messages=[], params={})

    assert result is None  # all attempts exhausted

    cur = await db.execute("SELECT status FROM agent_llm_tasks WHERE id = ?", (task_id,))
    row = await cur.fetchone()
    assert row["status"] == "dead_letter"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest llm_service/tests/test_executor.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# llm_service/runtime/executor.py
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

import aiosqlite

from llm_service.providers.base import ProviderError, ProviderProtocol
from llm_service.runtime.event_bus import EventBus
from llm_service.runtime.parser import ParseResult, parse_output
from llm_service.runtime.task_manager import TaskManager


class Executor:
    def __init__(
        self,
        db: aiosqlite.Connection,
        task_manager: TaskManager,
        event_bus: EventBus,
        provider: ProviderProtocol,
    ):
        self._db = db
        self._mgr = task_manager
        self._bus = event_bus
        self._provider = provider

    async def run(
        self,
        task_id: str,
        messages: list[dict],
        params: dict,
        expected_type: str = "json_object",
        schema: dict | None = None,
    ) -> ParseResult | None:
        """Execute task with retry loop. Returns ParseResult on success, None on exhaustion."""
        # Read request for this task
        cur = await self._db.execute("SELECT id FROM agent_llm_requests WHERE task_id = ?", (task_id,))
        row = await cur.fetchone()

        while True:
            # Get current attempt count
            cur = await self._db.execute("SELECT attempt_count FROM agent_llm_tasks WHERE id = ?", (task_id,))
            task_row = await cur.fetchone()
            attempt_no = task_row["attempt_count"] + 1

            attempt_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            await self._db.execute(
                """INSERT INTO agent_llm_attempts
                   (id, task_id, request_id, attempt_no, status, started_at)
                   VALUES (?, ?, ?, ?, 'running', ?)""",
                (attempt_id, task_id, row["id"] if row else "", attempt_no, now),
            )
            await self._db.commit()

            start = time.monotonic()
            try:
                resp = await self._provider.complete(messages=messages, params=params)
                latency = int((time.monotonic() - start) * 1000)
                finished = datetime.now(timezone.utc).isoformat()

                await self._db.execute(
                    """UPDATE agent_llm_attempts
                       SET status = 'succeeded', raw_output_text = ?, prompt_tokens = ?,
                           completion_tokens = ?, total_tokens = ?, latency_ms = ?, finished_at = ?,
                           raw_response_json = ?
                       WHERE id = ?""",
                    (resp.output_text, resp.prompt_tokens, resp.completion_tokens,
                     resp.total_tokens, latency, finished,
                     json.dumps(resp.raw_response or {}), attempt_id),
                )
                await self._db.commit()

                # Parse output
                parse_result = parse_output(resp.output_text, expected_type, schema)

                # Write result
                result_id = str(uuid.uuid4())
                await self._db.execute(
                    """INSERT INTO agent_llm_results
                       (id, task_id, attempt_id, parse_status, parsed_output_json, text_output,
                        parse_error, validation_errors_json, confidence, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (result_id, task_id, attempt_id, parse_result.parse_status,
                     json.dumps(parse_result.parsed_output or {}),
                     parse_result.text_output, parse_result.parse_error,
                     json.dumps(parse_result.validation_errors), None,
                     datetime.now(timezone.utc).isoformat()),
                )
                await self._db.commit()

                await self._mgr.complete(task_id)
                return parse_result

            except ProviderError as e:
                latency = int((time.monotonic() - start) * 1000)
                finished = datetime.now(timezone.utc).isoformat()
                await self._db.execute(
                    """UPDATE agent_llm_attempts
                       SET status = 'failed', error_type = ?, error_message = ?, latency_ms = ?, finished_at = ?
                       WHERE id = ?""",
                    (e.error_type, e.message, latency, finished, attempt_id),
                )
                await self._db.commit()

                # Check if retry is possible
                cur = await self._db.execute("SELECT max_attempts FROM agent_llm_tasks WHERE id = ?", (task_id,))
                t = await cur.fetchone()
                if attempt_no >= t["max_attempts"]:
                    await self._mgr.fail(task_id, e.error_type, e.message)
                    return None
                else:
                    await self._mgr.fail(task_id, e.error_type, e.message)
                    # Loop continues — task is back to queued, claim it again
                    # For single-process, directly continue the retry loop
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest llm_service/tests/test_executor.py -v`
Expected: 3 PASS

**Step 5: Commit**

```bash
git add llm_service/runtime/executor.py llm_service/tests/test_executor.py
git commit -m "[claude-llm]: T7 add executor with retry loop and attempt tracking"
```

---

## Phase 2: API Layer, Idempotency & Client

### Task 8: FastAPI Endpoints (tasks + execute + results + health)

**Files:**
- Create: `llm_service/api/__init__.py`
- Create: `llm_service/api/health.py`
- Create: `llm_service/api/tasks.py`
- Create: `llm_service/api/results.py`
- Modify: `llm_service/main.py`
- Test: `llm_service/tests/test_api.py`

**Step 1: Write the failing test** (tests for health, submit task, get task, execute)

```python
# llm_service/tests/test_api.py
import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


async def test_health_endpoint(tmp_path):
    from llm_service.main import create_app
    from llm_service.config import LLMServiceConfig

    cfg = LLMServiceConfig(db_path=str(tmp_path / "test.sqlite"))
    app = create_app(cfg)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


async def test_submit_task_endpoint(tmp_path):
    from llm_service.main import create_app
    from llm_service.config import LLMServiceConfig

    cfg = LLMServiceConfig(db_path=str(tmp_path / "test.sqlite"))
    app = create_app(cfg)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/tasks", json={
            "caller_domain": "mining",
            "pipeline_stage": "summary_generation",
            "template_key": "test-template",
            "input": {"text": "hello"},
            "params": {"temperature": 0.3},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "queued"


async def test_get_task_endpoint(tmp_path):
    from llm_service.main import create_app
    from llm_service.config import LLMServiceConfig

    cfg = LLMServiceConfig(db_path=str(tmp_path / "test.sqlite"))
    app = create_app(cfg)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Submit first
        resp = await client.post("/api/v1/tasks", json={
            "caller_domain": "mining",
            "pipeline_stage": "test",
        })
        task_id = resp.json()["task_id"]
        # Get
        resp = await client.get(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"
```

**Step 2-5: Implement then verify then commit** (follow same TDD pattern)

Implement `api/health.py`, `api/tasks.py`, `api/results.py`, wire them into `main.py` with proper startup/shutdown that initializes DB and runtime components.

Commit: `[claude-llm]: T8 add API endpoints for tasks, execute, results, health`

---

### Task 9: Prompt Template Registry

**Files:**
- Create: `llm_service/templates/__init__.py`
- Create: `llm_service/templates/registry.py`
- Create: `llm_service/api/templates.py`
- Test: `llm_service/tests/test_templates.py`

TDD: test create template → list templates → get by key/version → update status.

Commit: `[claude-llm]: T9 add prompt template registry CRUD`

---

### Task 10: Formal Client

**Files:**
- Create: `llm_service/client.py`
- Test: `llm_service/tests/test_client.py`

TDD: test submit_task, execute, get_task, get_result, cancel_task against ASGI test client.

Commit: `[claude-llm]: T10 add formal LLMClient for Mining/Serving integration`

---

## Phase 3: Dashboard

### Task 11: Dashboard Backend (Views + Stats API)

**Files:**
- Create: `llm_service/dashboard/__init__.py`
- Create: `llm_service/dashboard/views.py`
- Create: `llm_service/api/dashboard.py`
- Test: `llm_service/tests/test_dashboard.py`

TDD: test stats API returns correct counts, token usage aggregation.

Commit: `[claude-llm]: T11 add dashboard backend with stats API`

---

### Task 12: Dashboard Frontend (HTML + HTMX + CSS)

**Files:**
- Create: `llm_service/dashboard/templates/base.html`
- Create: `llm_service/dashboard/templates/index.html`
- Create: `llm_service/dashboard/templates/tasks.html`
- Create: `llm_service/dashboard/templates/task_detail.html`
- Create: `llm_service/dashboard/templates/templates_mgmt.html`
- Create: `llm_service/dashboard/templates/components/navbar.html`
- Create: `llm_service/dashboard/templates/components/task_table.html`
- Create: `llm_service/dashboard/templates/components/stats_cards.html`
- Create: `llm_service/static/css/dashboard.css`

Manual verification: start server, visit `/dashboard/`.

Commit: `[claude-llm]: T12 add Jinja2+HTMX dashboard frontend`

---

## Phase 4: Integration & Documentation

### Task 13: Full Integration Tests

**Files:**
- Create: `llm_service/tests/test_integration.py`

Tests covering the full chain: submit → execute → parse → result → events, idempotency, caller context passthrough, schema validation, failure recording, client round-trip.

Commit: `[claude-llm]: T13 add full integration tests`

---

### Task 14: README + Startup Script

**Files:**
- Create: `llm_service/README.md`
- Create: `llm_service/scripts/start.sh`

Commit: `[claude-llm]: T14 add README and startup script`

---

## Dependency Notes

- Tasks 1-7 are sequential (each builds on the previous)
- Tasks 8-10 depend on Tasks 1-7
- Tasks 11-12 depend on Task 8
- Tasks 13-14 depend on all previous

## Total: 14 Tasks, ~60 test cases
