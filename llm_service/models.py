from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


# --- Request models ---


class TaskSubmitRequest(BaseModel):
    caller_domain: str = Field(..., min_length=1, max_length=64)
    pipeline_stage: str = Field(..., pattern=r"^[a-z][a-z0-9_]{1,63}$")
    template_key: str | None = None
    input: dict[str, Any] | None = None
    messages: list[dict[str, Any]] | None = None
    params: dict[str, Any] | None = None
    expected_output_type: str | None = Field(
        default=None, pattern=r"^(json_object|json_array|text)$"
    )
    output_schema: dict[str, Any] | None = None
    idempotency_key: str | None = None
    metadata: dict[str, Any] | None = None
    max_attempts: int = Field(default=3, ge=1, le=10)
    priority: int = Field(default=100, ge=1)


# --- Response dataclasses ---


@dataclass
class ParsedResult:
    parse_status: str  # succeeded | failed | schema_invalid
    parsed_output: dict | list | None = None
    text_output: str | None = None
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
    metadata: dict[str, Any] | None
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
