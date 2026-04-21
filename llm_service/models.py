from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


# --- Request models ---


class TaskSubmitRequest(BaseModel):
    caller_domain: str = Field(..., pattern=r"^(mining|serving|evaluation|admin)$")
    pipeline_stage: str
    template_key: str | None = None
    input: dict[str, Any] | None = None
    messages: list[dict[str, Any]] | None = None
    params: dict[str, Any] | None = None
    expected_output_type: str = Field(
        default="json_object", pattern=r"^(json_object|json_array|text)$"
    )
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
