"""Real LLM integration tests — verifies Serving ↔ llm_service call chain.

These tests call the actual llm_service at localhost:8900.
They are skipped if the service is not available.

Covers:
1. LLMRuntimeClient.execute() → response parsing
2. LLMNormalizerProvider → real LLM query understanding
3. LLMPlannerProvider → real LLM plan generation
4. Full Serving /search pipeline with real LLM normalizer + planner
"""
from __future__ import annotations

import os

import pytest

from agent_serving.serving.schemas.models import NormalizedQuery, QueryPlan

# Skip entire module if LLM service not reachable
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LLM_INTEGRATION") == "1",
    reason="LLM integration tests disabled via SKIP_LLM_INTEGRATION=1",
)


def _llm_available() -> bool:
    """Check if llm_service is running and has serving templates."""
    try:
        import httpx

        resp = httpx.get("http://localhost:8900/api/v1/templates", timeout=5)
        if resp.status_code != 200:
            return False
        templates = resp.json()
        keys = {t["template_key"] for t in templates}
        return "serving-query-understanding" in keys and "serving-planner" in keys
    except Exception:
        return False


@pytest.fixture
def llm_client():
    """Create LLMRuntimeClient pointing at real service."""
    if not _llm_available():
        pytest.skip("llm_service not available or serving templates not registered")
    from agent_serving.serving.application.planner import LLMRuntimeClient

    return LLMRuntimeClient(base_url="http://localhost:8900")


# --- Test 1: LLMRuntimeClient raw call ---


class TestLLMRuntimeClient:
    @pytest.mark.asyncio
    async def test_execute_query_understanding(self, llm_client):
        """Verify LLMRuntimeClient.execute() returns correct structure."""
        result = await llm_client.execute(
            pipeline_stage="normalizer",
            template_key="serving-query-understanding",
            input={"query": "什么是5G网络"},
            expected_output_type="json_object",
        )

        # Response should have parsed_output
        assert "parsed_output" in result
        parsed = result["parsed_output"]
        assert isinstance(parsed, dict)
        assert "intent" in parsed
        assert "keywords" in parsed
        assert isinstance(parsed["keywords"], list)
        assert len(parsed["keywords"]) > 0

    @pytest.mark.asyncio
    async def test_execute_planner(self, llm_client):
        """Verify LLMRuntimeClient.execute() for planner stage."""
        result = await llm_client.execute(
            pipeline_stage="planner",
            template_key="serving-planner",
            input={
                "intent": "command_usage",
                "entities": [{"type": "command", "name": "ADD APN"}],
                "scope": {},
                "keywords": ["ADD", "APN"],
            },
            expected_output_type="json_object",
        )

        assert "parsed_output" in result
        parsed = result["parsed_output"]
        assert isinstance(parsed, dict)
        # Should return plan-related fields
        assert "desired_roles" in parsed or "budget" in parsed or "expansion" in parsed

    @pytest.mark.asyncio
    async def test_execute_with_nonexistent_template_returns_gracefully(self, llm_client):
        """Verify behavior when template doesn't exist — llm_service may return
        succeeded with empty parsed_output or error, both are acceptable."""
        result = await llm_client.execute(
            pipeline_stage="normalizer",
            template_key="nonexistent-template-xyz",
            input={"query": "test"},
            expected_output_type="json_object",
        )
        # llm_service returns result even for unknown templates
        assert isinstance(result, dict)


# --- Test 2: LLMNormalizerProvider with real LLM ---


class TestLLMNormalizerProviderIntegration:
    @pytest.mark.asyncio
    async def test_real_llm_normalize(self, llm_client):
        """Verify LLMNormalizerProvider calls real LLM and returns NormalizedQuery."""
        from agent_serving.serving.pipeline.llm_providers import LLMNormalizerProvider

        provider = LLMNormalizerProvider(llm_client=llm_client)
        result = await provider.normalize("如何配置AMF的SBI接口")

        assert result is not None
        assert isinstance(result, NormalizedQuery)
        assert result.original_query == "如何配置AMF的SBI接口"
        assert result.intent  # Should have some intent
        assert isinstance(result.keywords, list)

    @pytest.mark.asyncio
    async def test_real_llm_normalize_concept_query(self, llm_client):
        """Test concept query through real LLM."""
        from agent_serving.serving.pipeline.llm_providers import LLMNormalizerProvider

        provider = LLMNormalizerProvider(llm_client=llm_client)
        result = await provider.normalize("什么是网络切片")

        assert result is not None
        assert isinstance(result.keywords, list)
        assert len(result.keywords) > 0


# --- Test 3: LLMPlannerProvider with real LLM ---


class TestLLMPlannerProviderIntegration:
    @pytest.mark.asyncio
    async def test_real_llm_plan(self, llm_client):
        """Verify LLMPlannerProvider calls real LLM and returns QueryPlan."""
        from agent_serving.serving.pipeline.query_planner import LLMPlannerProvider

        provider = LLMPlannerProvider()
        provider.set_llm_client(llm_client)

        normalized = NormalizedQuery(
            original_query="ADD APN命令参数",
            intent="command_usage",
            keywords=["ADD", "APN", "命令", "参数"],
        )
        plan = await provider.abuild_plan(normalized)

        assert isinstance(plan, QueryPlan)
        assert plan.intent == "command_usage"
        assert isinstance(plan.budget.max_items, int)
        assert plan.budget.max_items > 0

    @pytest.mark.asyncio
    async def test_real_llm_plan_fallback_on_error(self):
        """Verify fallback to rule-based when LLM client has bad URL."""
        from agent_serving.serving.pipeline.query_planner import LLMPlannerProvider

        provider = LLMPlannerProvider()
        # No LLM client set → should fallback to rules
        normalized = NormalizedQuery(
            original_query="test",
            intent="general",
            keywords=["test"],
        )
        plan = await provider.abuild_plan(normalized)
        assert isinstance(plan, QueryPlan)
        assert plan.intent == "general"


# --- Test 4: QueryNormalizer.anormalize with real LLM ---


class TestQueryNormalizerIntegration:
    @pytest.mark.asyncio
    async def test_anormalize_with_real_llm(self, llm_client):
        """Verify QueryNormalizer.anormalize() uses real LLM then returns result."""
        from agent_serving.serving.application.normalizer import QueryNormalizer

        normalizer = QueryNormalizer(llm_client=llm_client)
        result = await normalizer.anormalize("查看UDM配置参数")

        assert isinstance(result, NormalizedQuery)
        assert result.original_query == "查看UDM配置参数"
        assert result.intent  # Some intent detected
        assert isinstance(result.keywords, list)

    @pytest.mark.asyncio
    async def test_anormalize_fallback_when_no_llm(self):
        """Verify anormalize falls back to rules when no LLM client."""
        from agent_serving.serving.application.normalizer import QueryNormalizer

        normalizer = QueryNormalizer()  # No LLM client
        result = await normalizer.anormalize("ADD APN命令怎么写")

        assert isinstance(result, NormalizedQuery)
        assert result.intent == "command_usage"
        assert len(result.entities) > 0
