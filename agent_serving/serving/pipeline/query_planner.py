"""QueryPlanner — transforms NormalizedQuery into executable QueryPlan.

v1.2: LLMPlannerProvider now uses LLMRuntimeClient.execute() for real calls.
Pluggable: rule-based default or LLM-backed provider.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from agent_serving.serving.schemas.models import (
    EntityRef,
    ExpansionConfig,
    NormalizedQuery,
    QueryPlan,
    RetrievalBudget,
)

logger = logging.getLogger(__name__)


class PlannerProvider(Protocol):
    """Interface for query planning providers."""

    def build_plan(
        self,
        normalized: NormalizedQuery,
        scope_override: dict | None = None,
        entities_override: list[EntityRef] | None = None,
    ) -> QueryPlan: ...


class RulePlannerProvider:
    """Rule-based query planner — deterministic default."""

    def build_plan(
        self,
        normalized: NormalizedQuery,
        scope_override: dict | None = None,
        entities_override: list[EntityRef] | None = None,
    ) -> QueryPlan:
        scope = scope_override if scope_override is not None else normalized.scope
        entities = entities_override if entities_override is not None else normalized.entities

        return QueryPlan(
            intent=normalized.intent,
            keywords=normalized.keywords,
            entity_constraints=entities,
            scope_constraints=scope,
            desired_roles=normalized.desired_roles,
            desired_block_types=[],
            budget=RetrievalBudget(),
            expansion=ExpansionConfig(),
        )


class LLMPlannerProvider:
    """LLM-backed query planner.

    v1.2: Uses LLMRuntimeClient.execute() with pipeline_stage="planner".
    Generates richer QueryPlan via LLM (multi-query decomposition,
    retriever selection, expansion strategy).
    Falls back to RulePlannerProvider when LLM is unavailable.
    """

    def __init__(self, fallback: PlannerProvider | None = None) -> None:
        self._fallback = fallback or RulePlannerProvider()
        self._llm_client: Any = None

    def set_llm_client(self, client: Any) -> None:
        """Set the LLM runtime client. Called during app init."""
        self._llm_client = client

    def build_plan(
        self,
        normalized: NormalizedQuery,
        scope_override: dict | None = None,
        entities_override: list[EntityRef] | None = None,
    ) -> QueryPlan:
        """Synchronous plan — rule-based only (fast path).

        For LLM path, use abuild_plan() instead.
        """
        return self._fallback.build_plan(normalized, scope_override, entities_override)

    async def abuild_plan(
        self,
        normalized: NormalizedQuery,
        scope_override: dict | None = None,
        entities_override: list[EntityRef] | None = None,
    ) -> QueryPlan:
        """Async plan — LLM first, rule-based fallback."""
        if self._llm_client and self._llm_client.is_available():
            try:
                return await self._try_llm_plan(normalized, scope_override, entities_override)
            except Exception:
                logger.warning("LLM planning failed, falling back to rules", exc_info=True)

        return self._fallback.build_plan(normalized, scope_override, entities_override)

    async def _try_llm_plan(
        self,
        normalized: NormalizedQuery,
        scope_override: dict | None,
        entities_override: list[EntityRef] | None,
    ) -> QueryPlan:
        """Call LLM runtime for structured plan generation."""
        from agent_serving.serving.application.planner import LLMRuntimeClient

        client = self._llm_client
        if not isinstance(client, LLMRuntimeClient):
            raise NotImplementedError("LLM client not configured")

        result = await client.execute(
            pipeline_stage="planner",
            template_key="serving-planner",
            input={
                "intent": normalized.intent,
                "entities": json.dumps([e.model_dump() for e in normalized.entities], ensure_ascii=False),
                "scope": json.dumps(normalized.scope, ensure_ascii=False),
                "keywords": ", ".join(normalized.keywords),
            },
            expected_output_type="json_object",
        )

        parsed = result.get("parsed_output", {})
        if not parsed:
            raise ValueError("Empty LLM plan response")

        budget_data = parsed.get("budget", {})
        budget = RetrievalBudget(
            max_items=int(budget_data.get("max_items", 10)),
            recall_multiplier=int(budget_data.get("recall_multiplier", 3)),
            max_expanded=int(budget_data.get("max_expanded", 5)),
        )

        return QueryPlan(
            intent=normalized.intent,
            keywords=normalized.keywords,
            entity_constraints=entities_override if entities_override is not None else normalized.entities,
            scope_constraints=scope_override if scope_override is not None else normalized.scope,
            desired_roles=parsed.get("desired_roles", normalized.desired_roles),
            desired_block_types=parsed.get("desired_block_types", []),
            budget=budget,
            expansion=ExpansionConfig(
                max_relation_depth=parsed.get("expansion", {}).get("max_depth", 2),
            ),
        )


class QueryPlanner:
    """Facade for query planning with pluggable provider."""

    def __init__(self, provider: PlannerProvider | None = None) -> None:
        self._provider = provider or RulePlannerProvider()

    def plan(
        self,
        normalized: NormalizedQuery,
        scope_override: dict | None = None,
        entities_override: list[EntityRef] | None = None,
    ) -> QueryPlan:
        return self._provider.build_plan(normalized, scope_override, entities_override)
