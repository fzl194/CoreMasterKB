"""Verify document profile module."""
from knowledge_mining.mining.document_profile import build_profile
from knowledge_mining.mining.models import RawDocumentData


def test_profile_from_manifest():
    doc = RawDocumentData(
        file_path="cmd/add_apn.md",
        content="ADD APN命令",
        manifest_meta={
            "doc_id": "cmd1",
            "doc_type": "command",
            "nf": ["UPF", "PGW-U"],
            "scenario_tags": ["command", "apn"],
            "source_type": "productdoc_export",
            "path": "cmd/add_apn.md",
        },
    )
    profile = build_profile(doc)
    assert profile.source_type == "productdoc_export"
    assert profile.document_type == "command"
    assert "UPF" in profile.scope_json.get("network_elements", [])
    assert "command" in profile.tags_json


def test_profile_from_frontmatter():
    doc = RawDocumentData(
        file_path="test.md",
        content="# Feature\n\nDescription",
        frontmatter={"source_type": "expert_authored", "product": "UDG5000"},
    )
    profile = build_profile(doc)
    assert profile.source_type == "expert_authored"
    assert profile.product == "UDG5000"


def test_profile_mml_command_detection():
    doc = RawDocumentData(
        file_path="test.md",
        content="ADD APN命令用于配置APN\n\n```\nADD APN\n```",
    )
    profile = build_profile(doc)
    assert profile.document_type == "command"


def test_expert_document_no_product():
    """Expert documents don't need product/version/NE."""
    doc = RawDocumentData(
        file_path="expert/notes.md",
        content="# 5G Core Design Notes\n\nSome expert observations...",
        frontmatter={"source_type": "expert_authored"},
    )
    profile = build_profile(doc)
    assert profile.source_type == "expert_authored"
    assert profile.product is None
    assert profile.scope_json == {}


def test_profile_no_metadata():
    doc = RawDocumentData(
        file_path="bare.md",
        content="Just some text without metadata.",
    )
    profile = build_profile(doc)
    assert profile.source_type == "other"
    assert profile.document_type is None


def test_profile_mixed_html_quality():
    doc = RawDocumentData(
        file_path="mixed.md",
        content="# Title\n\n<table><tr><td>data</td></tr></table>",
    )
    profile = build_profile(doc)
    assert profile.structure_quality == "mixed"
