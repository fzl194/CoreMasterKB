"""Hot-pluggable pipeline architecture for Mining v1.2.

Defines:
- DocumentContext: per-document immutable pipeline state
- Segmenter / RelationBuilder Protocols
- PipelineConfig: composable pipeline configuration
- MiningPipeline: orchestrates per-document processing
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from knowledge_mining.mining.models import (
    DocumentProfile,
    RawFileData,
    RawSegmentData,
    RetrievalUnitData,
    SectionNode,
    SegmentRelationData,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-document context (immutable between stages)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DocumentContext:
    """Per-document pipeline state, immutable between stages."""

    raw_file: RawFileData | None = None
    profile: DocumentProfile | None = None
    tree: SectionNode | None = None
    segments: tuple[RawSegmentData, ...] = ()
    relations: tuple[SegmentRelationData, ...] = ()
    seg_ids: dict[str, str] = field(default_factory=dict)
    retrieval_units: tuple[RetrievalUnitData, ...] = ()

    def with_updates(self, **kwargs: Any) -> DocumentContext:
        """Return a new DocumentContext with specified fields replaced."""
        current = {
            "raw_file": self.raw_file,
            "profile": self.profile,
            "tree": self.tree,
            "segments": self.segments,
            "relations": self.relations,
            "seg_ids": self.seg_ids,
            "retrieval_units": self.retrieval_units,
        }
        current.update(kwargs)
        return DocumentContext(**current)


# ---------------------------------------------------------------------------
# Operator Protocols
# ---------------------------------------------------------------------------

@runtime_checkable
class Segmenter(Protocol):
    """Protocol for splitting a SectionNode tree into segments."""

    def segment(
        self, tree: SectionNode, profile: DocumentProfile, **kwargs: Any,
    ) -> list[RawSegmentData]: ...


@runtime_checkable
class RelationBuilder(Protocol):
    """Protocol for building segment relations."""

    def build(
        self, segments: list[RawSegmentData], **kwargs: Any,
    ) -> tuple[list[SegmentRelationData], dict[str, str]]: ...


# ---------------------------------------------------------------------------
# Pipeline configuration
# ---------------------------------------------------------------------------

@dataclass
class PipelineConfig:
    """Composable pipeline configuration.

    Each field is a pluggable operator. Swap any operator to customize behavior.
    """

    parser_factory: Callable[[str], Any] = field(default=None)
    segmenter: Segmenter | None = None
    enricher: Any | None = None  # Enricher Protocol
    relation_builder: RelationBuilder | None = None
    question_generator: Any | None = None  # QuestionGenerator Protocol
    embedding_generator: Any | None = None  # EmbeddingGenerator Protocol
    discourse_relation_builder: Any | None = None  # DiscourseRelationBuilder
    contextualizer: Any | None = None  # Contextualizer Protocol


# ---------------------------------------------------------------------------
# Mining pipeline
# ---------------------------------------------------------------------------

class MiningPipeline:
    """Orchestrates per-document processing using pluggable operators."""

    def __init__(self, config: PipelineConfig) -> None:
        self._config = config

    @property
    def config(self) -> PipelineConfig:
        return self._config

    def process_document(
        self,
        ctx: DocumentContext,
        *,
        stage_callback: Any | None = None,
    ) -> DocumentContext:
        """Run all per-document pipeline stages.

        Args:
            ctx: Initial document context (must have raw_file set).
            stage_callback: Optional callback(stage_name, ctx) for tracking.

        Returns:
            Final DocumentContext with all stages populated.
        """
        cfg = self._config

        # Stage 1: Parse
        if stage_callback:
            stage_callback("parse", ctx)
        raw = ctx.raw_file
        if raw is None:
            return ctx
        parser = cfg.parser_factory(raw.file_type) if cfg.parser_factory else None
        if parser is None:
            return ctx
        tree = parser.parse(raw.content, raw.file_name, {})
        ctx = ctx.with_updates(tree=tree)

        if tree is None:
            return ctx

        # Stage 2: Segment
        if stage_callback:
            stage_callback("segment", ctx)
        seg = cfg.segmenter
        if seg is None:
            return ctx
        profile = ctx.profile
        if profile is None:
            return ctx
        segments = seg.segment(tree, profile)
        ctx = ctx.with_updates(segments=tuple(segments))

        # Stage 3: Enrich
        if stage_callback:
            stage_callback("enrich", ctx)
        enricher = cfg.enricher
        if enricher is not None and ctx.segments:
            enriched = enricher.enrich_batch(list(ctx.segments))
            ctx = ctx.with_updates(segments=tuple(enriched))

        # Stage 4: Build relations
        if stage_callback:
            stage_callback("build_relations", ctx)
        rb = cfg.relation_builder
        if rb is not None and ctx.segments:
            relations, seg_ids = rb.build(list(ctx.segments))
            ctx = ctx.with_updates(
                relations=tuple(relations),
                seg_ids=seg_ids,
            )

        # Stage 4b: Build discourse relations (LLM-driven RST analysis)
        drb = cfg.discourse_relation_builder
        if drb is not None and ctx.segments and ctx.seg_ids:
            if stage_callback:
                stage_callback("discourse_relations", ctx)
            extra_relations = drb.build(list(ctx.segments), seg_ids=ctx.seg_ids)
            if extra_relations:
                all_relations = list(ctx.relations) + extra_relations
                ctx = ctx.with_updates(relations=tuple(all_relations))

        # Stage 5: Build retrieval units
        if stage_callback:
            stage_callback("build_retrieval_units", ctx)
        if ctx.segments:
            from knowledge_mining.mining.retrieval_units import build_retrieval_units
            units = build_retrieval_units(
                list(ctx.segments),
                seg_ids=ctx.seg_ids,
                document_key=profile.document_key if profile else "",
                question_generator=cfg.question_generator,
                contextualizer=cfg.contextualizer,
            )
            ctx = ctx.with_updates(retrieval_units=tuple(units))

        return ctx
