"""Query Normalizer — extract entities, scope, and intent from queries.

Outputs a generic NormalizedQuery with entities[] + scope{} + intent.
Commands are just one entity type among many (command, feature, term, alarm).
build_plan() converts normalized query to a QueryPlan for repository use.

Domain patterns (products, NEs, versions, intent keywords) are loaded from
normalizer_config module, which supports YAML override via env var.
"""
from __future__ import annotations

import re

from agent_serving.serving.schemas.constants import (
    INTENT_COMMAND_USAGE,
    INTENT_CONCEPT_LOOKUP,
    INTENT_GENERAL,
    INTENT_PROCEDURE,
    INTENT_TROUBLESHOOT,
    POLICY_FLAG,
    POLICY_FLAG_NOT_ANSWER,
    POLICY_REQUIRE_DISAMBIGUATION,
)
from agent_serving.serving.schemas.models import (
    EntityRef,
    EvidenceBudget,
    ExpansionConfig,
    NormalizedQuery,
    QueryPlan,
    QueryScope,
)
from agent_serving.serving.application.normalizer_config import (
    DEFAULT_INTENT_COMMAND_KEYWORDS,
    DEFAULT_INTENT_CONCEPT_KEYWORDS,
    DEFAULT_INTENT_PROCEDURE_KEYWORDS,
    DEFAULT_INTENT_TROUBLESHOOT_KEYWORDS,
    DEFAULT_INTENT_ROLE_MAP,
    DEFAULT_OP_MAP,
    build_command_regex,
    build_ne_regex,
    build_product_regex,
    build_version_regex,
    load_config,
)


class QueryNormalizer:
    """Rule-based query normalizer with configurable domain patterns."""

    def __init__(self) -> None:
        cfg = load_config()
        self._command_re = build_command_regex()
        self._product_re = build_product_regex(cfg.get("products"))
        self._version_re = build_version_regex(cfg.get("version_pattern"))
        self._ne_re = build_ne_regex(cfg.get("network_elements"))
        self._op_map: dict[str, str] = cfg.get("op_map", DEFAULT_OP_MAP)

        intent_kw = cfg.get("intent_keywords", {})
        self._intent_command_keywords: set[str] = set(
            intent_kw.get("command", DEFAULT_INTENT_COMMAND_KEYWORDS)
        )
        self._intent_troubleshoot_keywords: set[str] = set(
            intent_kw.get("troubleshoot", DEFAULT_INTENT_TROUBLESHOOT_KEYWORDS)
        )
        self._intent_concept_keywords: set[str] = set(
            intent_kw.get("concept", DEFAULT_INTENT_CONCEPT_KEYWORDS)
        )
        self._intent_procedure_keywords: set[str] = set(
            intent_kw.get("procedure", DEFAULT_INTENT_PROCEDURE_KEYWORDS)
        )
        self._intent_role_map: dict[str, list[str]] = cfg.get(
            "intent_role_map", DEFAULT_INTENT_ROLE_MAP
        )

    def normalize(self, query: str) -> NormalizedQuery:
        entities = self._extract_entities(query)
        scope = self._extract_scope(query)
        intent = self._detect_intent(query, entities)
        keywords = self._extract_keywords(query)
        missing = self._find_missing(entities, scope, intent)
        desired_roles = self._desired_roles_for_intent(intent)

        return NormalizedQuery(
            intent=intent,
            entities=entities,
            scope=scope,
            keywords=keywords,
            desired_semantic_roles=desired_roles,
            missing_constraints=missing,
        )

    def _extract_entities(self, query: str) -> list[EntityRef]:
        entities: list[EntityRef] = []
        seen: set[str] = set()

        cmd = self._extract_command(query)
        if cmd:
            key = f"command:{cmd}"
            if key not in seen:
                entities.append(EntityRef(type="command", name=cmd, normalized_name=cmd))
                seen.add(key)

        return entities

    def _extract_command(self, query: str) -> str | None:
        match = self._command_re.search(query)
        if match:
            return f"{match.group(1).upper()} {match.group(2).upper()}"

        for cn_word, cmd_prefix in self._op_map.items():
            if cn_word in query:
                after = query.split(cn_word, 1)[-1]
                target_match = re.match(r"\s*([A-Za-z][A-Za-z0-9_]*)", after)
                if target_match:
                    target = target_match.group(1).upper()
                    return f"{cmd_prefix} {target}"
                return cmd_prefix
        return None

    def _extract_scope(self, query: str) -> QueryScope:
        products: set[str] = set()
        product_versions: list[str] = []
        network_elements: set[str] = set()

        for m in self._product_re.finditer(query):
            products.add(m.group(1).upper())

        v = self._version_re.search(query)
        if v:
            product_versions.append(v.group(1))

        for m in self._ne_re.finditer(query):
            network_elements.add(m.group(1).upper())

        return QueryScope(
            products=sorted(products),
            product_versions=product_versions,
            network_elements=sorted(network_elements),
        )

    def _detect_intent(self, query: str, entities: list[EntityRef]) -> str:
        has_command = any(e.type == "command" for e in entities)

        if has_command:
            return INTENT_COMMAND_USAGE

        for kw in self._intent_troubleshoot_keywords:
            if kw in query:
                return INTENT_TROUBLESHOOT

        for kw in self._intent_procedure_keywords:
            if kw in query:
                return INTENT_PROCEDURE

        for kw in self._intent_concept_keywords:
            if kw in query:
                return INTENT_CONCEPT_LOOKUP

        return INTENT_GENERAL

    def _extract_keywords(self, query: str) -> list[str]:
        cleaned = query
        for pattern in [self._command_re, self._product_re, self._version_re, self._ne_re]:
            cleaned = pattern.sub("", cleaned)
        tokens = [t for t in re.split(r"[\s,，、？?。.！!]+", cleaned) if len(t) > 0]
        return tokens

    def _find_missing(
        self, entities: list[EntityRef], scope: QueryScope, intent: str
    ) -> list[str]:
        missing: list[str] = []
        if intent == INTENT_COMMAND_USAGE:
            if not scope.products:
                missing.append("product")
            if scope.products and not scope.product_versions:
                missing.append("product_version")
        return missing

    def _desired_roles_for_intent(self, intent: str) -> list[str]:
        return list(self._intent_role_map.get(intent, []))


def build_plan(normalized: NormalizedQuery) -> QueryPlan:
    """Convert a normalized query into a QueryPlan.

    M1 uses simple rule-based planning. Future M2+ can replace this
    with LLM planner, ontology expansion, or multi-agent orchestration.
    """
    variant_policy = POLICY_FLAG
    if normalized.missing_constraints and normalized.intent == INTENT_COMMAND_USAGE:
        variant_policy = POLICY_REQUIRE_DISAMBIGUATION

    return QueryPlan(
        intent=normalized.intent,
        retrieval_targets=["canonical_segments"],
        entity_constraints=[
            EntityRef(type=e.type, name=e.name, normalized_name=e.normalized_name)
            for e in normalized.entities
        ],
        scope_constraints=QueryScope(
            products=list(normalized.scope.products),
            product_versions=list(normalized.scope.product_versions),
            network_elements=list(normalized.scope.network_elements),
            projects=list(normalized.scope.projects),
            domains=list(normalized.scope.domains),
        ),
        semantic_role_preferences=list(normalized.desired_semantic_roles),
        block_type_preferences=list(normalized.desired_block_types),
        variant_policy=variant_policy,
        conflict_policy=POLICY_FLAG_NOT_ANSWER,
        evidence_budget=EvidenceBudget(canonical_limit=10, raw_per_canonical=3),
        expansion=ExpansionConfig(use_ontology=False, max_hops=0),
        keywords=list(normalized.keywords),
    )
