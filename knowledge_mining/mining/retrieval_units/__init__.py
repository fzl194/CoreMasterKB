"""Retrieval units stage: build retrieval-ready units from segments for v1.1.

v1.1 produces:
- raw_text: one-to-one from each segment
- contextual_text: segment with section heading context prepended
- entity_card: one per unique entity from entity_refs (deduped across segments)
- generated_question: placeholder for LLM-generated questions (v1.1: empty when no LLM Runtime)

v1.2 will add:
- LLM-backed generated_question via LlmQuestionGenerator protocol
- summary (LLM-generated)
"""
from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

from knowledge_mining.mining.models import RawSegmentData, RetrievalUnitData


@runtime_checkable
class QuestionGenerator(Protocol):
    """Protocol for generating retrieval questions from segments.

    v1.1: NoOpQuestionGenerator returns empty (LLM Runtime not yet integrated).
    v1.2: LlmQuestionGenerator calls LLM Runtime to generate questions.
    """
    def generate(self, segment: RawSegmentData) -> list[str]:
        """Return list of generated questions for the segment."""
        ...


class NoOpQuestionGenerator:
    """v1.1 default: no questions generated (LLM Runtime not yet integrated)."""

    def generate(self, segment: RawSegmentData) -> list[str]:
        return []


def build_retrieval_units(
    segments: list[RawSegmentData],
    *,
    document_key: str = "",
    question_generator: QuestionGenerator | None = None,
) -> list[RetrievalUnitData]:
    """Build retrieval units from segments."""
    if not segments:
        return []

    qgen = question_generator or NoOpQuestionGenerator()
    units: list[RetrievalUnitData] = []
    seen_entity_cards: set[str] = set()

    for seg in segments:
        # 1. raw_text unit (1:1 with segment)
        units.append(_make_raw_text_unit(seg))

        # 2. contextual_text unit (segment + section context)
        ctx_unit = _make_contextual_text_unit(seg)
        if ctx_unit is not None:
            units.append(ctx_unit)

        # 3. entity_card units (deduped)
        for ref in seg.entity_refs_json:
            entity_key = f"{ref.get('type', '')}:{ref.get('name', '')}"
            if entity_key not in seen_entity_cards:
                seen_entity_cards.add(entity_key)
                units.append(_make_entity_card_unit(seg, ref))

        # 4. generated_question units (v1.1: empty unless LLM Runtime provided)
        questions = qgen.generate(seg)
        for qi, question in enumerate(questions):
            units.append(_make_generated_question_unit(seg, question, qi))

    return units


def _make_raw_text_unit(seg: RawSegmentData) -> RetrievalUnitData:
    """One-to-one raw_text retrieval unit from segment."""
    return RetrievalUnitData(
        segment_key=f"{seg.document_key}#{seg.segment_index}",
        unit_key=f"ru:{seg.document_key}#{seg.segment_index}:raw_text",
        unit_type="raw_text",
        target_type="raw_segment",
        target_ref_json={
            "document_key": seg.document_key,
            "segment_index": seg.segment_index,
        },
        title=seg.section_title,
        text=seg.raw_text,
        search_text=seg.raw_text,
        block_type=seg.block_type,
        semantic_role=seg.semantic_role,
        facets_json=_build_facets(seg),
        entity_refs_json=list(seg.entity_refs_json),
        source_refs_json=_build_source_refs(seg),
        weight=1.0,
        metadata_json={"segment_index": seg.segment_index},
    )


def _make_contextual_text_unit(seg: RawSegmentData) -> RetrievalUnitData | None:
    """Contextual text: raw_text with section path prepended."""
    if not seg.section_path or seg.block_type == "heading":
        return None

    section_titles = [p.get("title", "") for p in seg.section_path if p.get("title")]
    context_prefix = " > ".join(section_titles)
    if not context_prefix:
        return None

    contextual_text = f"[{context_prefix}]\n{seg.raw_text}"

    return RetrievalUnitData(
        segment_key=f"{seg.document_key}#{seg.segment_index}",
        unit_key=f"ru:{seg.document_key}#{seg.segment_index}:contextual_text",
        unit_type="contextual_text",
        target_type="raw_segment",
        target_ref_json={
            "document_key": seg.document_key,
            "segment_index": seg.segment_index,
        },
        title=seg.section_title,
        text=contextual_text,
        search_text=contextual_text,
        block_type=seg.block_type,
        semantic_role=seg.semantic_role,
        facets_json=_build_facets(seg),
        entity_refs_json=list(seg.entity_refs_json),
        source_refs_json=_build_source_refs(seg),
        weight=0.9,
        metadata_json={
            "section_titles": section_titles,
            "segment_index": seg.segment_index,
        },
    )


def _make_entity_card_unit(
    seg: RawSegmentData,
    ref: dict[str, str],
) -> RetrievalUnitData:
    """Entity card: one per unique entity reference."""
    entity_type = ref.get("type", "unknown")
    entity_name = ref.get("name", "unknown")

    text = f"{entity_name} ({entity_type})"
    if seg.section_title:
        text += f" — 见 {seg.section_title}"

    return RetrievalUnitData(
        segment_key=f"{seg.document_key}#{seg.segment_index}",
        unit_key=f"ru:entity:{entity_type}:{entity_name}",
        unit_type="entity_card",
        target_type="entity",
        target_ref_json={"entity_type": entity_type, "entity_name": entity_name},
        title=entity_name,
        text=text,
        search_text=f"{entity_name} {entity_type}",
        block_type=seg.block_type,
        semantic_role=seg.semantic_role,
        facets_json={"entity_type": entity_type},
        entity_refs_json=[ref],
        source_refs_json=_build_source_refs(seg),
        weight=0.5,
        metadata_json={"first_seen_in": seg.document_key},
    )


def _make_generated_question_unit(
    seg: RawSegmentData,
    question: str,
    question_index: int,
) -> RetrievalUnitData:
    """Generated question unit: one per LLM-generated question."""
    return RetrievalUnitData(
        segment_key=f"{seg.document_key}#{seg.segment_index}",
        unit_key=f"ru:{seg.document_key}#{seg.segment_index}:gen_q_{question_index}",
        unit_type="generated_question",
        target_type="raw_segment",
        target_ref_json={
            "document_key": seg.document_key,
            "segment_index": seg.segment_index,
            "question_index": question_index,
        },
        title=question[:80],
        text=question,
        search_text=question,
        block_type=seg.block_type,
        semantic_role=seg.semantic_role,
        facets_json=_build_facets(seg),
        entity_refs_json=list(seg.entity_refs_json),
        source_refs_json=_build_source_refs(seg),
        llm_result_refs_json={"source": "llm_runtime", "question_index": question_index},
        weight=0.7,
        metadata_json={"question_index": question_index},
    )


def _build_facets(seg: RawSegmentData) -> dict[str, Any]:
    """Build facets from segment metadata."""
    facets: dict[str, Any] = {}
    if seg.block_type:
        facets["block_type"] = seg.block_type
    if seg.semantic_role:
        facets["semantic_role"] = seg.semantic_role
    if seg.section_path:
        facets["section_depth"] = len(seg.section_path)
    return facets


def _build_source_refs(seg: RawSegmentData) -> dict[str, Any]:
    """Build source_refs for provenance tracing."""
    refs: dict[str, Any] = {
        "document_key": seg.document_key,
        "segment_index": seg.segment_index,
    }
    if seg.source_offsets_json:
        refs["offsets"] = seg.source_offsets_json
    return refs
