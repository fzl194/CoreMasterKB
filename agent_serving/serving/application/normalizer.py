"""Query Normalizer — v1.1 rewrite.

Two-layer design:
1. LLM Runtime client for intelligent query understanding (when available)
2. Rule-based fallback for deterministic extraction

Outputs NormalizedQuery with entities, scope, keywords, intent.
"""
from __future__ import annotations

import re

from agent_serving.serving.schemas.constants import (
    INTENT_COMMAND_USAGE,
    INTENT_CONCEPT_LOOKUP,
    INTENT_GENERAL,
    INTENT_PROCEDURE,
    INTENT_TROUBLESHOOT,
)
from agent_serving.serving.schemas.models import (
    EntityRef,
    NormalizedQuery,
)
from agent_serving.serving.application.normalizer_config import NormalizerConfig
from agent_serving.serving.application.planner import LLMRuntimeClient


# --- Default patterns ---

_DEFAULT_COMMAND_RE = re.compile(
    r"(ADD|MOD|DEL|SET|SHOW|LST|DSP)\s+([A-Z][A-Z0-9_]*)",
    re.IGNORECASE,
)

_DEFAULT_OP_MAP: dict[str, str] = {
    "新增": "ADD", "添加": "ADD", "创建": "ADD",
    "修改": "MOD", "更改": "MOD", "编辑": "MOD",
    "删除": "DEL", "移除": "DEL",
    "查询": "SHOW", "查看": "DSP", "显示": "LST",
    "设置": "SET", "配置": "SET",
}

_DEFAULT_PRODUCTS: list[str] = ["UDG", "UNC", "CloudCore"]
_DEFAULT_NETWORK_ELEMENTS: list[str] = [
    "AMF", "SMF", "UPF", "UDM", "PCF", "NRF",
    "AUSF", "BSF", "NSSF", "SCP", "UDSF", "UDR",
]
_DEFAULT_VERSION_PATTERN = r"(V\d{3}R\d{3}(C\d{2})?)"

_INTENT_COMMAND_KW = {"命令", "用法", "参数", "格式", "语法", "怎么写", "如何配置"}
_INTENT_TROUBLESHOOT_KW = {"故障", "排查", "告警", "错误", "异常", "处理"}
_INTENT_CONCEPT_KW = {"是什么", "什么是", "概念", "介绍", "概述", "原理"}
_INTENT_PROCEDURE_KW = {"步骤", "流程", "操作", "怎么做", "如何操作"}

_INTENT_ROLE_MAP: dict[str, list[str]] = {
    "command_usage": ["parameter", "example", "procedure_step"],
    "troubleshooting": ["troubleshooting_step", "alarm", "constraint"],
    "concept_lookup": ["concept", "note"],
    "procedure": ["procedure_step", "parameter", "example"],
    "general": [],
}

_STOPWORDS_ZH = {
    "的", "了", "在", "是", "和", "与", "及", "或", "也", "都",
    "这", "那", "有", "没", "不", "会", "能", "要", "可以",
    "什么", "怎么", "如何", "哪些", "为什么", "吗", "呢", "啊",
    "个", "一", "到", "把", "被", "让", "给", "从", "对", "等",
    "请问", "帮我", "告诉", "知道", "想", "应该", "需要",
}
_STOPWORDS_EN = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "do", "does", "did", "has", "have", "had",
    "and", "or", "but", "not", "no", "in", "on", "at", "to",
    "of", "for", "with", "from", "by", "as",
    "what", "which", "how", "why", "when", "where", "who",
}
_ALL_STOPWORDS = _STOPWORDS_ZH | _STOPWORDS_EN


class QueryNormalizer:
    """Two-layer normalizer: LLM-first, rule-based fallback."""

    def __init__(
        self,
        llm_client: LLMRuntimeClient | None = None,
        config: NormalizerConfig | None = None,
    ) -> None:
        self._llm = llm_client
        self._cfg = config or NormalizerConfig()

    def normalize(self, query: str) -> NormalizedQuery:
        """Normalize query. LLM path when available, rule-based fallback."""
        if self._llm and self._llm.is_available():
            llm_result = self._try_llm_normalize(query)
            if llm_result:
                return llm_result

        return self._rule_normalize(query)

    def _try_llm_normalize(self, query: str) -> NormalizedQuery | None:
        """Attempt LLM-based normalization. Returns None on failure."""
        # v1.1: LLM normalization not yet connected
        # Future: call self._llm.complete() with structured prompt
        return None

    def _rule_normalize(self, query: str) -> NormalizedQuery:
        """Rule-based normalization with regex patterns."""
        entities = self._extract_entities(query)
        scope = self._extract_scope(query)
        intent = self._detect_intent(query, entities)
        keywords = self._extract_keywords(query)
        desired_roles = _INTENT_ROLE_MAP.get(intent, [])

        return NormalizedQuery(
            original_query=query,
            intent=intent,
            entities=entities,
            scope=scope,
            keywords=keywords,
            desired_roles=desired_roles,
        )

    def _extract_entities(self, query: str) -> list[EntityRef]:
        entities: list[EntityRef] = []
        cmd = self._extract_command(query)
        if cmd:
            entities.append(EntityRef(type="command", name=cmd, normalized_name=cmd))
        return entities

    def _extract_command(self, query: str) -> str | None:
        match = _DEFAULT_COMMAND_RE.search(query)
        if match:
            return f"{match.group(1).upper()} {match.group(2).upper()}"

        for cn_word, cmd_prefix in _DEFAULT_OP_MAP.items():
            if cn_word in query:
                after = query.split(cn_word, 1)[-1]
                target_match = re.match(r"\s*([A-Za-z][A-Za-z0-9_]*)", after)
                if target_match:
                    return f"{cmd_prefix} {target_match.group(1).upper()}"
                return cmd_prefix
        return None

    def _extract_scope(self, query: str) -> dict:
        scope: dict = {}
        # Use word boundary for English context, but also match adjacent to CJK
        product_re = re.compile(
            r"(?:^|(?<=[\s,，、\(（]))(" + "|".join(re.escape(p) for p in _DEFAULT_PRODUCTS) + r")(?=[\s,，、\)）]|$)",
            re.IGNORECASE,
        )
        # Fallback: simple substring match (CJK context)
        products = set()
        for p in _DEFAULT_PRODUCTS:
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(p)}(?![A-Za-z0-9_])", query, re.IGNORECASE):
                products.add(p.upper())
        if products:
            scope["products"] = sorted(products)

        v = re.compile(_DEFAULT_VERSION_PATTERN).search(query)
        if v:
            scope["product_versions"] = [v.group(1)]

        nes = set()
        for n in _DEFAULT_NETWORK_ELEMENTS:
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(n)}(?![A-Za-z0-9_])", query, re.IGNORECASE):
                nes.add(n.upper())
        if nes:
            scope["network_elements"] = sorted(nes)

        return scope

    def _detect_intent(self, query: str, entities: list[EntityRef]) -> str:
        if any(e.type == "command" for e in entities):
            return INTENT_COMMAND_USAGE
        for kw in _INTENT_TROUBLESHOOT_KW:
            if kw in query:
                return INTENT_TROUBLESHOOT
        for kw in _INTENT_PROCEDURE_KW:
            if kw in query:
                return INTENT_PROCEDURE
        for kw in _INTENT_CONCEPT_KW:
            if kw in query:
                return INTENT_CONCEPT_LOOKUP
        return INTENT_GENERAL

    def _extract_keywords(self, query: str) -> list[str]:
        cleaned = _DEFAULT_COMMAND_RE.sub("", query)
        tokens = [t for t in re.split(r"[\s,，、？?。.！!]+", cleaned) if t]
        return [
            t for t in tokens
            if t not in _ALL_STOPWORDS and len(t) >= 2
        ]
