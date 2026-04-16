"""Segmentation module: split SectionNode tree into L0 RawSegmentData."""
from __future__ import annotations

import re

from knowledge_mining.mining.models import ContentBlock, DocumentProfile, RawSegmentData, SectionNode
from knowledge_mining.mining.text_utils import (
    content_hash,
    normalized_hash,
    token_count,
)

_CMD_PATTERN = re.compile(r"^(ADD|MOD|DEL|SET|DSP|LST|SHOW)\s+[A-Z0-9_]+", re.MULTILINE)

_ROLE_KEYWORDS: dict[str, list[str]] = {
    "parameter": ["参数", "parameter"],
    "example": ["示例", "举例", "example"],
    "note": ["注意", "备注", "note", "注意事"],
    "precondition": ["前置", "前提", "precondition"],
    "procedure_step": ["步骤", "操作步骤", "配置步骤"],
    "troubleshooting_step": ["排障", "故障处理", "troubleshooting"],
    "concept_intro": ["概述", "介绍", "简介"],
}

_BLOCK_TO_SEGMENT: dict[str, str] = {
    "table": "table",
    "html_table": "table",
    "code": "example",
    "list": "paragraph",
    "paragraph": "paragraph",
    "heading": "paragraph",
    "blockquote": "paragraph",
    "raw_html": "other",
    "unknown": "other",
}


def segment_document(
    doc_root: SectionNode,
    profile: DocumentProfile,
) -> list[RawSegmentData]:
    """Split document section tree into raw segments."""
    segments: list[RawSegmentData] = []
    _walk_sections(doc_root, profile.file_path, [], segments)
    return [
        RawSegmentData(
            document_file_path=s.document_file_path,
            segment_index=idx,
            section_path=s.section_path,
            section_title=s.section_title,
            heading_level=s.heading_level,
            segment_type=s.segment_type,
            block_type=s.block_type,
            section_role=s.section_role,
            raw_text=s.raw_text,
            normalized_text=s.normalized_text,
            content_hash=s.content_hash,
            normalized_hash=s.normalized_hash,
            token_count=s.token_count,
            command_name=s.command_name,
            structure_json=s.structure_json,
            source_offsets_json=s.source_offsets_json,
        )
        for idx, s in enumerate(segments)
    ]


def _walk_sections(
    node: SectionNode,
    file_path: str,
    parent_path: list[str],
    segments: list[RawSegmentData],
) -> None:
    """Recursively walk section tree, creating segments."""
    current_path = list(parent_path)
    if node.title:
        current_path.append(node.title)

    section_role = _infer_section_role(node.title)
    current_group: list[ContentBlock] = []

    for block in node.blocks:
        if block.block_type in ("table", "html_table", "code"):
            if current_group:
                segments.append(
                    _make_segment(file_path, current_path, node, current_group, section_role)
                )
                current_group = []
            segments.append(
                _make_segment(file_path, current_path, node, [block], section_role)
            )
        else:
            current_group.append(block)

    if current_group:
        segments.append(
            _make_segment(file_path, current_path, node, current_group, section_role)
        )

    for child in node.children:
        _walk_sections(child, file_path, current_path, segments)


def _make_segment(
    file_path: str,
    section_path: list[str],
    section: SectionNode,
    blocks: list[ContentBlock],
    section_role: str | None,
) -> RawSegmentData:
    """Create a RawSegmentData from a group of content blocks."""
    primary_block = blocks[0] if blocks else None
    block_type = primary_block.block_type if primary_block else "unknown"

    raw_text = "\n\n".join(b.text for b in blocks)
    norm_text = raw_text.lower().strip()
    cmd_match = _CMD_PATTERN.search(raw_text)

    structure_json = _extract_structure_info(blocks)

    return RawSegmentData(
        document_file_path=file_path,
        segment_index=0,
        section_path=section_path,
        section_title=section.title,
        heading_level=section.level if section.title else None,
        segment_type=_BLOCK_TO_SEGMENT.get(block_type, "other"),
        block_type=block_type,
        section_role=section_role,
        raw_text=raw_text,
        normalized_text=norm_text,
        content_hash=content_hash(raw_text),
        normalized_hash=normalized_hash(raw_text),
        token_count=token_count(raw_text),
        command_name=cmd_match.group(0) if cmd_match else None,
        structure_json=structure_json,
    )


def _infer_section_role(title: str | None) -> str | None:
    if not title:
        return None
    for role, keywords in _ROLE_KEYWORDS.items():
        for kw in keywords:
            if kw in title:
                return role
    return None


def _extract_structure_info(blocks: list[ContentBlock]) -> dict:
    info: dict = {}
    for block in blocks:
        if block.block_type == "table":
            lines = block.text.split(" | ")
            info["estimated_columns"] = len(lines)
        elif block.block_type == "html_table":
            info["is_html_table"] = True
            info["estimated_rows"] = block.text.lower().count("<tr")
        elif block.block_type == "code":
            if block.language:
                info["language"] = block.language
    return info
