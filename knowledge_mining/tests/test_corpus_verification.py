"""Task 12: Boundary tests for real corpus scenarios."""
import tempfile
from pathlib import Path

from knowledge_mining.mining.canonicalization import canonicalize
from knowledge_mining.mining.document_profile import build_profile
from knowledge_mining.mining.ingestion import ingest_directory
from knowledge_mining.mining.jobs.run import run_pipeline
from knowledge_mining.mining.models import RawSegmentData
from knowledge_mining.mining.segmentation import segment_document
from knowledge_mining.mining.structure import parse_structure


def _write_files(tmp: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        p = tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def test_no_manifest_plain_markdown():
    """No manifest, no frontmatter — pure directory scan works."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_files(tmp, {
            "doc.md": "# Plain\n\nJust text",
        })
        summary = run_pipeline(tmp, tmp / "test.sqlite")
        assert summary["documents"] == 1
        assert summary["segments"] >= 1


def test_expert_doc_no_product():
    """Expert document without product/version/NE."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_files(tmp, {
            "expert.md": "---\nsource_type: expert_authored\n---\n# 5G Core Notes\n\nExpert observations.",
        })
        docs = ingest_directory(tmp)
        profile = build_profile(docs[0])
        assert profile.source_type == "expert_authored"
        assert profile.product is None


def test_html_table_in_markdown():
    """Markdown with HTML table preserved as html_table block."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_files(tmp, {
            "doc.md": "# Data\n\n<table>\n<tr><td>A</td></tr>\n</table>",
        })
        docs = ingest_directory(tmp)
        profile = build_profile(docs[0])
        root = parse_structure(docs[0].content)
        segments = segment_document(root, profile)
        html_table_segs = [s for s in segments if s.block_type == "html_table"]
        assert len(html_table_segs) >= 1


def test_manifest_no_nf_field():
    """Document in manifest without nf field."""
    import json
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_files(tmp, {"doc.md": "# Title\n\nContent"})
        manifest = [{"doc_id": "d1", "doc_type": "feature", "nf": [],
                     "scenario_tags": [], "source_type": "synthetic_coldstart",
                     "path": "doc.md"}]
        (tmp / "manifest.jsonl").write_text(
            json.dumps(manifest[0]), encoding="utf-8"
        )
        docs = ingest_directory(tmp)
        profile = build_profile(docs[0])
        assert "network_elements" not in profile.scope_json  # empty nf list not added
