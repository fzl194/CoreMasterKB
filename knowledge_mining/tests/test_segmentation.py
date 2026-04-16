"""Verify segmentation: block_type, section_role, hash, command_name."""
from knowledge_mining.mining.document_profile import build_profile
from knowledge_mining.mining.models import RawDocumentData
from knowledge_mining.mining.segmentation import segment_document
from knowledge_mining.mining.structure import parse_structure


def _make_profile(content: str, file_path: str = "test.md") -> tuple:
    doc = RawDocumentData(file_path=file_path, content=content)
    profile = build_profile(doc)
    root = parse_structure(content)
    segments = segment_document(root, profile)
    return profile, segments


def test_single_paragraph_segment():
    _, segments = _make_profile("# Title\n\nHello world")
    assert len(segments) >= 1
    para_segs = [s for s in segments if s.block_type == "paragraph"]
    assert len(para_segs) >= 1


def test_table_segment():
    _, segments = _make_profile(
        "# Data\n\n| A | B |\n|---|---|\n| 1 | 2 |"
    )
    table_segs = [s for s in segments if s.block_type == "table"]
    assert len(table_segs) >= 1


def test_html_table_segment():
    _, segments = _make_profile(
        '# Table\n\n<table>\n<tr><td>A</td><td>B</td></tr>\n</table>'
    )
    html_table_segs = [s for s in segments if s.block_type == "html_table"]
    assert len(html_table_segs) >= 1


def test_code_segment():
    _, segments = _make_profile("# Code\n\n```mml\nADD APN\n```")
    code_segs = [s for s in segments if s.block_type == "code"]
    assert len(code_segs) >= 1


def test_section_role_parameter():
    _, segments = _make_profile("# 参数说明\n\nAPN名称：test")
    role_segs = [s for s in segments if s.section_role == "parameter"]
    assert len(role_segs) >= 1


def test_command_name_detection():
    _, segments = _make_profile("ADD APN命令用于配置APN")
    cmd_segs = [s for s in segments if s.command_name == "ADD APN"]
    assert len(cmd_segs) >= 1


def test_hashes_computed():
    _, segments = _make_profile("# Title\n\nContent")
    for seg in segments:
        assert seg.content_hash != ""
        assert seg.normalized_hash != ""
        assert len(seg.content_hash) == 64


def test_token_count_positive():
    _, segments = _make_profile("# Title\n\nHello world")
    for seg in segments:
        assert seg.token_count is not None
        assert seg.token_count >= 0


def test_section_path_correct():
    _, segments = _make_profile("# Root\n\n## Sub\n\nContent")
    sub_segs = [s for s in segments if s.section_title == "Sub"]
    assert len(sub_segs) >= 1
    assert "Root" in sub_segs[0].section_path


def test_segment_indices_sequential():
    _, segments = _make_profile("# A\n\nPara1\n\n## B\n\nPara2\n\n## C\n\nPara3")
    for i, seg in enumerate(segments):
        assert seg.segment_index == i
