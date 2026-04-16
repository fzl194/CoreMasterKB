"""Verify canonicalization: exact, near, approximate dedup + variant detection."""
from knowledge_mining.mining.canonicalization import canonicalize
from knowledge_mining.mining.models import (
    CanonicalSegmentData,
    DocumentProfile,
    RawSegmentData,
    SourceMappingData,
)


def _make_seg(file_path: str, idx: int, raw_text: str, **kwargs) -> RawSegmentData:
    from knowledge_mining.mining.text_utils import content_hash, normalized_hash, token_count
    return RawSegmentData(
        document_file_path=file_path,
        segment_index=idx,
        section_path=["Root"],
        section_title="Root",
        heading_level=1,
        segment_type=kwargs.get("segment_type", "paragraph"),
        block_type=kwargs.get("block_type", "paragraph"),
        section_role=kwargs.get("section_role"),
        raw_text=raw_text,
        normalized_text=raw_text.lower(),
        content_hash=content_hash(raw_text),
        normalized_hash=normalized_hash(raw_text),
        token_count=token_count(raw_text),
        command_name=kwargs.get("command_name"),
    )


def test_single_segment_creates_primary():
    segs = [_make_seg("a.md", 0, "Hello world")]
    profiles = {"a.md": DocumentProfile(file_path="a.md")}
    canonicals, mappings = canonicalize(segs, profiles)
    assert len(canonicals) == 1
    assert len(mappings) == 1
    assert mappings[0].relation_type == "primary"


def test_exact_duplicate_merged():
    text = "Identical content"
    segs = [
        _make_seg("a.md", 0, text),
        _make_seg("b.md", 0, text),
    ]
    profiles = {
        "a.md": DocumentProfile(file_path="a.md"),
        "b.md": DocumentProfile(file_path="b.md"),
    }
    canonicals, mappings = canonicalize(segs, profiles)
    assert len(canonicals) == 1
    assert len(mappings) == 2
    rel_types = {m.relation_type for m in mappings}
    assert "primary" in rel_types
    assert "exact_duplicate" in rel_types


def test_product_variant():
    text = "Same content different products"
    segs = [
        _make_seg("a.md", 0, text),
        _make_seg("b.md", 0, text),
    ]
    profiles = {
        "a.md": DocumentProfile(file_path="a.md", product="UDG5000"),
        "b.md": DocumentProfile(file_path="b.md", product="UDG6000"),
    }
    canonicals, mappings = canonicalize(segs, profiles)
    assert len(canonicals) == 1
    assert canonicals[0].has_variants is True
    rel_types = {m.relation_type for m in mappings}
    assert "product_variant" in rel_types


def test_version_variant():
    text = "Same content different versions"
    segs = [
        _make_seg("a.md", 0, text),
        _make_seg("b.md", 0, text),
    ]
    profiles = {
        "a.md": DocumentProfile(file_path="a.md", product="UDG", product_version="V1"),
        "b.md": DocumentProfile(file_path="b.md", product="UDG", product_version="V2"),
    }
    canonicals, mappings = canonicalize(segs, profiles)
    assert len(canonicals) == 1
    assert canonicals[0].has_variants is True


def test_no_duplicate_independent():
    segs = [
        _make_seg("a.md", 0, "Content A"),
        _make_seg("b.md", 0, "Content B is very different from A"),
    ]
    profiles = {
        "a.md": DocumentProfile(file_path="a.md"),
        "b.md": DocumentProfile(file_path="b.md"),
    }
    canonicals, mappings = canonicalize(segs, profiles)
    assert len(canonicals) == 2


def test_empty_input():
    canonicals, mappings = canonicalize([], {})
    assert canonicals == []
    assert mappings == []
