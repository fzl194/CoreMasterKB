"""Enrich stage: rule-based semantic enrichment for v1.1.

v1.1 enrich does:
- Refine semantic_role based on structural context
- Enhance entity_refs with section-level context
- Compute metadata_json fields for downstream stages

v1.2 will replace this with LLM-based extraction.
"""
from __future__ import annotations

from typing import Any

from knowledge_mining.mining.models import RawSegmentData


def enrich_segments(
    segments: list[RawSegmentData],
    *,
    context: dict[str, Any] | None = None,
) -> list[RawSegmentData]:
    """Apply rule-based enrichment to segments. Returns new list (immutable)."""
    ctx = context or {}
    enriched: list[RawSegmentData] = []
    for seg in segments:
        enriched.append(_enrich_one(seg, ctx))
    return enriched


def _enrich_one(seg: RawSegmentData, ctx: dict[str, Any]) -> RawSegmentData:
    """Enrich a single segment. Returns a new frozen instance."""
    changes: dict[str, Any] = {}

    # 1. Enhance entity_refs with section context
    entity_refs = list(seg.entity_refs_json)
    if seg.section_title:
        entity_refs = _add_section_context_entities(seg.section_title, entity_refs)
    if entity_refs != list(seg.entity_refs_json):
        changes["entity_refs_json"] = entity_refs

    # 2. Enrich metadata with structural hints
    meta = dict(seg.metadata_json)
    if seg.block_type == "heading" and seg.section_title:
        meta["heading_role"] = _classify_heading_role(seg.section_title)
    if seg.block_type == "table" and seg.structure_json:
        cols = seg.structure_json.get("columns", [])
        if cols:
            meta["table_column_count"] = len(cols)
            meta["table_has_parameter_column"] = any("参数" in c for c in cols)
    if changes or meta != dict(seg.metadata_json):
        changes["metadata_json"] = meta

    if not changes:
        return seg

    # Create new frozen instance with changes
    return RawSegmentData(
        document_key=seg.document_key,
        segment_index=seg.segment_index,
        block_type=seg.block_type,
        semantic_role=changes.get("semantic_role", seg.semantic_role),
        section_path=seg.section_path,
        section_title=seg.section_title,
        raw_text=seg.raw_text,
        normalized_text=seg.normalized_text,
        content_hash=seg.content_hash,
        normalized_hash=seg.normalized_hash,
        token_count=seg.token_count,
        structure_json=seg.structure_json,
        source_offsets_json=seg.source_offsets_json,
        entity_refs_json=changes.get("entity_refs_json", seg.entity_refs_json),
        metadata_json=changes.get("metadata_json", seg.metadata_json),
    )


_HEADING_ROLE_KEYWORDS: list[tuple[list[str], str]] = [
    (["参数", "参数说明", "参数标识"], "parameter_definition"),
    (["使用实例", "示例", "配置示例"], "example_section"),
    (["操作步骤", "流程", "检查项"], "procedure_section"),
    (["排障", "故障"], "troubleshooting_section"),
    (["注意事项", "限制", "约束"], "constraint_section"),
    (["概述", "简介", "功能"], "overview_section"),
]


def _classify_heading_role(title: str) -> str:
    title_lower = title.lower()
    for keywords, role in _HEADING_ROLE_KEYWORDS:
        if any(kw.lower() in title_lower for kw in keywords):
            return role
    return "section"


def _add_section_context_entities(
    section_title: str,
    existing: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Add section-title-derived entities if not already present."""
    seen = {(r["type"], r["name"]) for r in existing}

    # Check if title itself is a command-like pattern
    import re
    cmd_match = re.match(r"^(ADD|SHOW|MOD|DEL|DSP|LST|REG|DEREG)\s+(\S+)", section_title.upper())
    if cmd_match:
        cmd_name = f"{cmd_match.group(1)} {cmd_match.group(2)}"
        key = ("command", cmd_name)
        if key not in seen:
            existing.append({"type": "command", "name": cmd_name})

    return existing
