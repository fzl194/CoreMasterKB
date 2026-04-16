"""Verify ingestion module with manifest.jsonl and plain Markdown."""
import json
import tempfile
from pathlib import Path

from knowledge_mining.mining.ingestion import ingest_directory


def _write_files(tmp: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        p = tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def test_ingest_plain_markdown_no_metadata():
    """No manifest, no frontmatter — still imports."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_files(tmp, {
            "doc1.md": "# Hello\n\nWorld",
            "sub/doc2.md": "# Sub\n\nContent",
        })
        docs = ingest_directory(tmp)
        assert len(docs) == 2
        assert docs[0].file_path == "doc1.md"
        assert "# Hello" in docs[0].content
        assert docs[0].manifest_meta == {}


def test_ingest_with_frontmatter():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_files(tmp, {
            "doc.md": "---\ntitle: Test\nproduct: UDG\n---\n# Content",
        })
        docs = ingest_directory(tmp)
        assert len(docs) == 1
        assert docs[0].frontmatter.get("title") == "Test"
        assert docs[0].frontmatter.get("product") == "UDG"


def test_ingest_manifest():
    """Mode A: manifest.jsonl driven."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_files(tmp, {
            "docs/cmd1.md": "# ADD APN\n\nConfigure APN",
            "docs/feat1.md": "# Feature\n\nDescription",
        })
        manifest = [
            {"doc_id": "cmd1", "title": "ADD APN", "doc_type": "command",
             "nf": ["UPF"], "scenario_tags": ["command"],
             "source_type": "productdoc_export", "path": "docs/cmd1.md"},
            {"doc_id": "feat1", "title": "Feature", "doc_type": "feature",
             "nf": ["SMF"], "scenario_tags": ["feature"],
             "source_type": "synthetic_coldstart", "path": "docs/feat1.md"},
        ]
        (tmp / "manifest.jsonl").write_text(
            "\n".join(json.dumps(m) for m in manifest), encoding="utf-8"
        )
        docs = ingest_directory(tmp)
        assert len(docs) == 2
        assert docs[0].manifest_meta["doc_id"] == "cmd1"
        assert docs[0].manifest_meta["source_type"] == "productdoc_export"
        assert docs[1].manifest_meta["doc_type"] == "feature"


def test_ingest_manifest_missing_file_skipped():
    """Missing files in manifest are skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_files(tmp, {
            "docs/exists.md": "# Exists",
        })
        manifest = [
            {"doc_id": "exists", "path": "docs/exists.md", "doc_type": "feature",
             "nf": [], "scenario_tags": [], "source_type": "other"},
            {"doc_id": "missing", "path": "docs/missing.md", "doc_type": "feature",
             "nf": [], "scenario_tags": [], "source_type": "other"},
        ]
        (tmp / "manifest.jsonl").write_text(
            "\n".join(json.dumps(m) for m in manifest), encoding="utf-8"
        )
        docs = ingest_directory(tmp)
        assert len(docs) == 1


def test_ingest_empty_directory():
    with tempfile.TemporaryDirectory() as tmp:
        docs = ingest_directory(Path(tmp))
        assert docs == []


def test_ingest_skips_non_markdown():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_files(tmp, {
            "doc.md": "# MD",
            "data.txt": "text file",
            "image.png": "fake",
        })
        docs = ingest_directory(tmp)
        assert len(docs) == 1
        assert docs[0].file_path == "doc.md"
