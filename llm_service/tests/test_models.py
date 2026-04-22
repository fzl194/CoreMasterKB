import pytest
from llm_service.models import (
    TaskSubmitRequest,
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
            caller_domain="",
            pipeline_stage="test",
        )

    with pytest.raises(ValueError):
        TaskSubmitRequest(
            caller_domain="x" * 65,
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
