"""Pipeline data objects for M1 Knowledge Mining — aligned with asset schema v0.5."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BatchParams:
    """Batch-level parameters passed from CLI or future frontend."""

    default_source_type: str = "folder_scan"
    default_document_type: str | None = None
    batch_scope: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    storage_root_uri: str | None = None
    original_root_name: str | None = None


@dataclass(frozen=True)
class RawDocumentData:
    """Output of ingestion: raw document content + v0.5 metadata."""

    file_path: str
    relative_path: str
    file_name: str
    file_type: str  # markdown, html, pdf, doc, docx, txt, other
    content: str
    content_hash: str
    source_uri: str = ""
    source_type: str | None = None
    document_type: str | None = None
    title: str | None = None
    scope_json: dict[str, Any] = field(default_factory=dict)
    tags_json: list[str] = field(default_factory=list)
    structure_quality: str = "unknown"
    processing_profile_json: dict[str, Any] = field(default_factory=dict)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentProfile:
    """Document classification derived from BatchParams + file metadata."""

    document_key: str
    source_type: str = "other"
    document_type: str | None = None
    scope_json: dict[str, Any] = field(default_factory=dict)
    tags_json: list[str] = field(default_factory=list)
    structure_quality: str = "unknown"
    title: str | None = None


@dataclass(frozen=True)
class ContentBlock:
    """A parsed content block from the structure parser."""

    block_type: str  # heading, paragraph, list, table, html_table, code, blockquote, raw_html, unknown
    text: str
    language: str | None = None
    level: int | None = None  # heading level
    line_start: int | None = None  # 0-based line number from markdown-it token.map
    line_end: int | None = None
    structure: dict[str, Any] | None = None  # structured content (table columns/rows, list items, etc.)


@dataclass(frozen=True)
class SectionNode:
    """A section in the document tree."""

    title: str | None
    level: int
    children: tuple[SectionNode, ...] = ()
    blocks: tuple[ContentBlock, ...] = ()


@dataclass(frozen=True)
class RawSegmentData:
    """L0 segment output from segmentation — aligned with v0.5 raw_segments."""

    document_key: str
    segment_index: int
    block_type: str = "unknown"
    semantic_role: str = "unknown"
    section_path: list[dict[str, Any]] = field(default_factory=list)
    section_title: str | None = None
    raw_text: str = ""
    normalized_text: str = ""
    content_hash: str = ""
    normalized_hash: str = ""
    token_count: int | None = None
    structure_json: dict[str, Any] = field(default_factory=dict)
    source_offsets_json: dict[str, Any] = field(default_factory=dict)
    entity_refs_json: list[dict[str, str]] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalSegmentData:
    """L1 canonical segment after dedup — aligned with v0.5 canonical_segments."""

    canonical_key: str
    block_type: str = "unknown"
    semantic_role: str = "unknown"
    canonical_text: str = ""
    search_text: str = ""
    title: str | None = None
    summary: str | None = None
    entity_refs_json: list[dict[str, str]] = field(default_factory=list)
    scope_json: dict[str, Any] = field(default_factory=dict)
    has_variants: bool = False
    variant_policy: str = "none"
    quality_score: float | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)
    raw_segment_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourceMappingData:
    """L2 source mapping: canonical → raw segments — aligned with v0.5."""

    canonical_key: str
    raw_segment_ref: str
    relation_type: str  # primary, exact_duplicate, normalized_duplicate, near_duplicate, scope_variant, conflict_candidate
    is_primary: bool = False
    priority: int = 100
    similarity_score: float | None = None
    diff_summary: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)
