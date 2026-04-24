"""Tests for mining pipeline bug fixes (Phase 1) and hot-pluggable architecture (Phase 2)."""
from __future__ import annotations

import pytest

from knowledge_mining.mining.models import (
    ContentBlock,
    DocumentProfile,
    RawSegmentData,
    RetrievalUnitData,
    SectionNode,
)


# ===================================================================
# Phase 1: Bug Fix Tests
# ===================================================================

class TestNestedListParsing:
    """Bug 1: Structure parser should preserve nested list items."""

    def test_nested_list_items_preserved(self):
        """Nested list sub-items should appear in items_nested."""
        from knowledge_mining.mining.structure import parse_structure

        md = """## Steps

1. Configure Flowfilter
   - Sub-item A
   - Sub-item B
2. Set policy
   - Sub-item C
3. Apply rule
"""
        tree = parse_structure(md)
        blocks = _collect_blocks(tree)
        list_blocks = [b for b in blocks if b.block_type == "list"]
        assert len(list_blocks) >= 1

        main_list = list_blocks[0]
        struct = main_list.structure
        assert struct is not None

        # Flat items should only contain depth-1 items
        assert "Configure Flowfilter" in struct["items"]
        assert "Set policy" in struct["items"]
        assert "Apply rule" in struct["items"]

        # Nested items should include all depths
        items_nested = struct.get("items_nested", [])
        nested_texts = [it["text"] for it in items_nested]
        assert "Sub-item A" in nested_texts, f"Sub-item A missing from {nested_texts}"
        assert "Sub-item B" in nested_texts
        assert "Sub-item C" in nested_texts

    def test_nested_list_hierarchical_text(self):
        """ContentBlock.text should contain indented hierarchical text."""
        from knowledge_mining.mining.structure import parse_structure

        md = """## Steps

1. Step one
   - Detail A
   - Detail B
2. Step two
"""
        tree = parse_structure(md)
        blocks = _collect_blocks(tree)
        list_blocks = [b for b in blocks if b.block_type == "list"]
        assert len(list_blocks) >= 1

        text = list_blocks[0].text
        # Top-level items should have "1." prefix
        assert "1. Step one" in text
        assert "2. Step two" in text
        # Sub-items should be indented with "  -"
        assert "  - Detail A" in text or "- Detail A" in text

    def test_backward_compat_flat_items(self):
        """items field should still work with only depth-1 items."""
        from knowledge_mining.mining.structure import parse_structure

        md = """- Apple
- Banana
- Cherry
"""
        tree = parse_structure(md)
        blocks = _collect_blocks(tree)
        list_blocks = [b for b in blocks if b.block_type == "list"]
        assert len(list_blocks) >= 1

        struct = list_blocks[0].structure
        assert struct["items"] == ["Apple", "Banana", "Cherry"]
        # items_nested should have same items with depth=1
        assert all(it["depth"] == 1 for it in struct["items_nested"])


class TestGeneratedQuestionDifferentiation:
    """Bug 2: generated_question title/text/search_text should differ."""

    def test_question_unit_fields_differ(self):
        from knowledge_mining.mining.retrieval_units import _make_generated_question_unit

        seg = RawSegmentData(
            document_key="doc:/test.md",
            segment_index=5,
            block_type="paragraph",
            section_title="参数说明",
            raw_text="这是一个关于网络配置参数的详细说明段落，包含多个关键参数。",
            section_path=[{"title": "参数说明", "level": 2}],
        )

        unit = _make_generated_question_unit(seg, "如何配置网络参数？", 0)

        # title should have Q prefix
        assert unit.title.startswith("Q1:")
        assert "如何配置网络参数" in unit.title

        # text should include source context
        assert "如何配置网络参数？" in unit.text
        assert "来源" in unit.text
        assert "参数说明" in unit.text

        # search_text should include section title (tokenized)
        # jieba may split "参数说明" into tokens, so check for presence of key chars
        assert "参数" in unit.search_text or "参数说明" in unit.search_text

        # All three should be different
        assert unit.title != unit.text
        assert unit.text != unit.search_text
        assert unit.title != unit.search_text

    def test_question_unit_second_index(self):
        from knowledge_mining.mining.retrieval_units import _make_generated_question_unit

        seg = RawSegmentData(
            document_key="doc:/test.md",
            segment_index=0,
            block_type="paragraph",
            raw_text="test content",
        )
        unit = _make_generated_question_unit(seg, "What is this?", 1)
        assert unit.title.startswith("Q2:")


class TestQuestionGenerationFilter:
    """Bug 3: heading-only and very short segments should not generate questions."""

    def test_heading_segments_filtered(self):
        from knowledge_mining.mining.retrieval_units import _is_questionworthy

        heading_seg = RawSegmentData(
            document_key="doc:/test.md",
            segment_index=0,
            block_type="heading",
            raw_text="参数说明",
        )
        assert _is_questionworthy(heading_seg) is False

    def test_short_segments_filtered(self):
        from knowledge_mining.mining.retrieval_units import _is_questionworthy

        short_seg = RawSegmentData(
            document_key="doc:/test.md",
            segment_index=0,
            block_type="paragraph",
            raw_text="too short",  # < 15 chars
        )
        assert _is_questionworthy(short_seg) is False

    def test_low_token_segments_filtered(self):
        from knowledge_mining.mining.retrieval_units import _is_questionworthy

        low_token_seg = RawSegmentData(
            document_key="doc:/test.md",
            segment_index=0,
            block_type="paragraph",
            raw_text="some content that is long enough",
            token_count=5,  # < 10
        )
        assert _is_questionworthy(low_token_seg) is False

    def test_normal_segments_pass(self):
        from knowledge_mining.mining.retrieval_units import _is_questionworthy

        good_seg = RawSegmentData(
            document_key="doc:/test.md",
            segment_index=0,
            block_type="paragraph",
            raw_text="This is a normal paragraph with enough content to be considered question-worthy.",
            token_count=15,
        )
        assert _is_questionworthy(good_seg) is True

    def test_filter_in_build_retrieval_units(self):
        """Verify heading segments are not sent to question generator."""
        from knowledge_mining.mining.retrieval_units import build_retrieval_units

        segments = [
            RawSegmentData(
                document_key="doc:/test.md",
                segment_index=0,
                block_type="heading",
                raw_text="Title Only",
                section_title="Title Only",
            ),
            RawSegmentData(
                document_key="doc:/test.md",
                segment_index=1,
                block_type="paragraph",
                raw_text="This is a substantial paragraph with enough content to generate questions from.",
                token_count=15,
                section_title="Title Only",
            ),
        ]

        # Mock question generator to track which segments it receives
        received_keys: list[str] = []

        class MockQGen:
            def generate(self, segment):
                return ["Q?"]

            def generate_batch(self, segments):
                for s in segments:
                    received_keys.append(f"{s.document_key}#{s.segment_index}")
                return {f"{s.document_key}#{s.segment_index}": ["Generated Q?"] for s in segments}

        units = build_retrieval_units(
            segments,
            document_key="doc:/test.md",
            question_generator=MockQGen(),
        )

        # Only the paragraph should have received questions
        assert "doc:/test.md#0" not in received_keys, "Heading segment should not be sent to QGen"
        assert "doc:/test.md#1" in received_keys


class TestContextualTextImprovements:
    """Bug 4: contextual_text should not be simple title+raw_text concatenation."""

    def test_table_contextual_is_nl_description(self):
        from knowledge_mining.mining.retrieval_units import _make_contextual_text_unit

        seg = RawSegmentData(
            document_key="doc:/test.md",
            segment_index=0,
            block_type="table",
            section_title="参数列表",
            raw_text="Param | Type | Desc\nVal1 | Str | Desc1",
            structure_json={
                "columns": ["Param", "Type", "Desc"],
                "rows": [
                    {"Param": "Name", "Type": "String", "Desc": "The name"},
                    {"Param": "Age", "Type": "Int", "Desc": "The age"},
                ],
            },
        )

        unit = _make_contextual_text_unit(seg)
        assert unit is not None
        # Should be natural language, not raw pipe-delimited text
        assert "列包括" in unit.text
        assert "Param" in unit.text
        assert unit.weight == 0.6

    def test_list_contextual_uses_nested(self):
        from knowledge_mining.mining.retrieval_units import _make_contextual_text_unit

        seg = RawSegmentData(
            document_key="doc:/test.md",
            segment_index=0,
            block_type="list",
            section_title="配置步骤",
            raw_text="Step 1\nStep 2",
            structure_json={
                "items": ["Step 1", "Step 2"],
                "items_nested": [
                    {"text": "Step 1", "depth": 1},
                    {"text": "detail A", "depth": 2},
                    {"text": "Step 2", "depth": 1},
                ],
            },
        )

        unit = _make_contextual_text_unit(seg)
        assert unit is not None
        assert "配置步骤" in unit.text
        assert "主要条目" in unit.text or "条目" in unit.text

    def test_paragraph_contextual_only_when_section_adds_info(self):
        from knowledge_mining.mining.retrieval_units import _make_contextual_text_unit

        # Section title already in raw_text -> no contextual
        seg1 = RawSegmentData(
            document_key="doc:/test.md",
            segment_index=0,
            block_type="paragraph",
            raw_text="This is the 参数说明 section content",
            section_path=[{"title": "参数说明", "level": 2}],
            section_title="参数说明",
        )
        unit1 = _make_contextual_text_unit(seg1)
        # Should return empty because section title is already in raw_text
        assert unit1 is None or "参数说明" not in (unit1.text if unit1 else "")

    def test_heading_never_gets_contextual(self):
        from knowledge_mining.mining.retrieval_units import _make_contextual_text_unit

        seg = RawSegmentData(
            document_key="doc:/test.md",
            segment_index=0,
            block_type="heading",
            raw_text="Title",
            section_title="Title",
        )
        assert _make_contextual_text_unit(seg) is None


class TestTableRowUnits:
    """Bug 1 supplement: table segments should produce per-row retrieval units."""

    def test_table_row_units_generated(self):
        from knowledge_mining.mining.retrieval_units import _make_table_row_units

        seg = RawSegmentData(
            document_key="doc:/test.md",
            segment_index=0,
            block_type="table",
            raw_text="table text",
            structure_json={
                "columns": ["用户类型", "业务类型", "业务需求"],
                "rows": [
                    {"用户类型": "普通用户", "业务类型": "视频业务", "业务需求": "高带宽"},
                    {"用户类型": "企业用户", "业务类型": "数据业务", "业务需求": "低延迟"},
                ],
            },
        )

        units = _make_table_row_units(seg)
        assert len(units) == 2

        # First row
        u0 = units[0]
        assert u0.unit_type == "table_row"
        assert "用户类型为普通用户" in u0.text
        assert "业务类型为视频业务" in u0.text
        assert u0.weight == 0.8

        # Second row
        u1 = units[1]
        assert "企业用户" in u1.text
        assert "低延迟" in u1.text

    def test_table_row_units_in_build(self):
        from knowledge_mining.mining.retrieval_units import build_retrieval_units

        seg = RawSegmentData(
            document_key="doc:/test.md",
            segment_index=0,
            block_type="table",
            raw_text="table text",
            structure_json={
                "columns": ["A", "B"],
                "rows": [{"A": "a1", "B": "b1"}],
            },
        )

        units = build_retrieval_units([seg], document_key="doc:/test.md")
        table_rows = [u for u in units if u.unit_type == "table_row"]
        assert len(table_rows) == 1

    def test_non_table_produces_no_row_units(self):
        from knowledge_mining.mining.retrieval_units import _make_table_row_units

        seg = RawSegmentData(
            document_key="doc:/test.md",
            segment_index=0,
            block_type="paragraph",
            raw_text="not a table",
        )
        assert _make_table_row_units(seg) == []


# ===================================================================
# Phase 2: Pipeline Architecture Tests
# ===================================================================

class TestDocumentContext:
    """DocumentContext should be immutable and support with_updates."""

    def test_immutable(self):
        from knowledge_mining.mining.pipeline import DocumentContext

        ctx = DocumentContext()
        with pytest.raises(AttributeError):
            ctx.segments = ()  # type: ignore

    def test_with_updates(self):
        from knowledge_mining.mining.pipeline import DocumentContext

        ctx = DocumentContext()
        seg = RawSegmentData(document_key="doc:/test.md", segment_index=0)
        ctx2 = ctx.with_updates(segments=(seg,))
        assert len(ctx2.segments) == 1
        assert len(ctx.segments) == 0  # original unchanged


class TestPipelineConfig:
    """PipelineConfig should accept pluggable operators."""

    def test_default_config(self):
        from knowledge_mining.mining.pipeline import PipelineConfig

        config = PipelineConfig()
        assert config.segmenter is None
        assert config.enricher is None

    def test_custom_segmenter(self):
        from knowledge_mining.mining.pipeline import PipelineConfig

        class CustomSegmenter:
            def segment(self, tree, profile, **kwargs):
                return []

        config = PipelineConfig(segmenter=CustomSegmenter())
        assert isinstance(config.segmenter, CustomSegmenter)


class TestDefaultSegmenter:
    """DefaultSegmenter should wrap segment_document."""

    def test_delegates_to_segment_document(self):
        from knowledge_mining.mining.segmentation import DefaultSegmenter
        from knowledge_mining.mining.structure import parse_structure

        md = "# Title\n\nParagraph content here.\n"
        tree = parse_structure(md)
        profile = DocumentProfile(document_key="doc:/test.md")

        segmenter = DefaultSegmenter()
        segments = segmenter.segment(tree, profile)
        assert len(segments) > 0
        assert all(isinstance(s, RawSegmentData) for s in segments)


class TestDefaultRelationBuilder:
    """DefaultRelationBuilder should wrap build_relations."""

    def test_delegates_to_build_relations(self):
        from knowledge_mining.mining.relations import DefaultRelationBuilder

        segments = [
            RawSegmentData(document_key="doc:/test.md", segment_index=0, block_type="heading"),
            RawSegmentData(document_key="doc:/test.md", segment_index=1, block_type="paragraph"),
        ]

        builder = DefaultRelationBuilder()
        relations, seg_ids = builder.build(segments)
        assert len(relations) > 0
        assert len(seg_ids) == 2


class TestMiningPipeline:
    """MiningPipeline should orchestrate per-document processing."""

    def test_process_document_full_flow(self):
        from knowledge_mining.mining.pipeline import DocumentContext, PipelineConfig, MiningPipeline
        from knowledge_mining.mining.parsers import create_parser
        from knowledge_mining.mining.segmentation import DefaultSegmenter
        from knowledge_mining.mining.enrich import RuleBasedEnricher
        from knowledge_mining.mining.relations import DefaultRelationBuilder
        from knowledge_mining.mining.extractors import RuleBasedEntityExtractor, DefaultRoleClassifier
        from knowledge_mining.mining.models import RawFileData

        content = "# Test Doc\n\nParagraph about ADD APN command.\n\n## Section\n\nMore content.\n"
        raw_file = RawFileData(
            file_path="/test/test.md",
            relative_path="test.md",
            file_name="test.md",
            file_type="markdown",
            content=content,
            raw_content_hash="rh1",
            normalized_content_hash="nh1",
        )
        profile = DocumentProfile(document_key="doc:/test.md", title="Test Doc")

        config = PipelineConfig(
            parser_factory=create_parser,
            segmenter=DefaultSegmenter(),
            enricher=RuleBasedEnricher(
                entity_extractor=RuleBasedEntityExtractor(),
                role_classifier=DefaultRoleClassifier(),
            ),
            relation_builder=DefaultRelationBuilder(),
        )
        pipeline = MiningPipeline(config)

        ctx = DocumentContext(raw_file=raw_file, profile=profile)
        result = pipeline.process_document(ctx)

        assert result.tree is not None
        assert len(result.segments) > 0
        assert len(result.relations) > 0
        assert len(result.retrieval_units) > 0
        assert result.seg_ids  # should have segment ID mappings

    def test_process_document_with_stage_callback(self):
        from knowledge_mining.mining.pipeline import DocumentContext, PipelineConfig, MiningPipeline
        from knowledge_mining.mining.parsers import create_parser
        from knowledge_mining.mining.segmentation import DefaultSegmenter
        from knowledge_mining.mining.enrich import RuleBasedEnricher
        from knowledge_mining.mining.relations import DefaultRelationBuilder
        from knowledge_mining.mining.extractors import RuleBasedEntityExtractor, DefaultRoleClassifier
        from knowledge_mining.mining.models import RawFileData

        content = "# Title\n\nParagraph.\n"
        raw_file = RawFileData(
            file_path="/test/test.md",
            relative_path="test.md",
            file_name="test.md",
            file_type="markdown",
            content=content,
            raw_content_hash="rh",
            normalized_content_hash="nh",
        )
        profile = DocumentProfile(document_key="doc:/test.md")

        stages_called: list[str] = []

        config = PipelineConfig(
            parser_factory=create_parser,
            segmenter=DefaultSegmenter(),
            enricher=RuleBasedEnricher(),
            relation_builder=DefaultRelationBuilder(),
        )
        pipeline = MiningPipeline(config)
        ctx = DocumentContext(raw_file=raw_file, profile=profile)

        def callback(stage_name, current_ctx):
            stages_called.append(stage_name)

        pipeline.process_document(ctx, stage_callback=callback)

        assert "parse" in stages_called
        assert "segment" in stages_called
        assert "enrich" in stages_called
        assert "build_relations" in stages_called
        assert "build_retrieval_units" in stages_called

    def test_custom_operator_swap(self):
        """Verify pipeline works when swapping DefaultSegmenter with custom."""
        from knowledge_mining.mining.pipeline import DocumentContext, PipelineConfig, MiningPipeline
        from knowledge_mining.mining.parsers import create_parser
        from knowledge_mining.mining.relations import DefaultRelationBuilder
        from knowledge_mining.mining.models import RawFileData

        content = "# Title\n\nText.\n"
        raw_file = RawFileData(
            file_path="/test/test.md",
            relative_path="test.md",
            file_name="test.md",
            file_type="markdown",
            content=content,
            raw_content_hash="rh",
            normalized_content_hash="nh",
        )
        profile = DocumentProfile(document_key="doc:/test.md")

        class SingleSegSegmenter:
            """Custom segmenter that produces exactly one segment."""
            def segment(self, tree, profile, **kwargs):
                return [RawSegmentData(
                    document_key=profile.document_key,
                    segment_index=0,
                    block_type="paragraph",
                    raw_text="Custom segment",
                )]

        config = PipelineConfig(
            parser_factory=create_parser,
            segmenter=SingleSegSegmenter(),
            enricher=None,
            relation_builder=DefaultRelationBuilder(),
        )
        pipeline = MiningPipeline(config)
        ctx = DocumentContext(raw_file=raw_file, profile=profile)
        result = pipeline.process_document(ctx)

        assert len(result.segments) == 1
        assert result.segments[0].raw_text == "Custom segment"


class TestLlmTemplates:
    """Verify new template is registered."""

    def test_segment_understanding_template_exists(self):
        from knowledge_mining.mining.llm_templates import TEMPLATES

        keys = [t["template_key"] for t in TEMPLATES]
        assert "mining-segment-understanding" in keys

    def test_segment_understanding_template_structure(self):
        from knowledge_mining.mining.llm_templates import TEMPLATES

        tpl = next(t for t in TEMPLATES if t["template_key"] == "mining-segment-understanding")
        assert tpl["expected_output_type"] == "json_object"
        assert "entities" in tpl["user_prompt_template"]
        assert "semantic_role" in tpl["user_prompt_template"]


# ===================================================================
# Helpers
# ===================================================================

def _collect_blocks(node: SectionNode) -> list[ContentBlock]:
    blocks = list(node.blocks)
    for child in node.children:
        blocks.extend(_collect_blocks(child))
    return blocks
