"""Ingestion module: read manifest.jsonl or scan plain Markdown directories."""
from __future__ import annotations

import json
from pathlib import Path

from knowledge_mining.mining.models import RawDocumentData


def ingest_directory(input_path: Path) -> list[RawDocumentData]:
    """Ingest documents from a directory.

    Mode A: If manifest.jsonl exists, use it to drive ingestion.
    Mode B: Otherwise, recursively scan .md files.
    """
    input_path = Path(input_path)
    manifest_path = input_path / "manifest.jsonl"
    if manifest_path.exists():
        return _ingest_with_manifest(input_path, manifest_path)
    return _ingest_plain_markdown(input_path)


def _ingest_with_manifest(input_path: Path, manifest_path: Path) -> list[RawDocumentData]:
    """Mode A: manifest.jsonl driven ingestion."""
    results: list[RawDocumentData] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        meta = json.loads(line)
        doc_path = input_path / meta["path"]
        if not doc_path.exists():
            continue
        content = doc_path.read_text(encoding="utf-8")
        frontmatter = _parse_frontmatter(content)
        results.append(
            RawDocumentData(
                file_path=str(meta["path"]),
                content=content,
                frontmatter=frontmatter,
                manifest_meta=meta,
            )
        )
    return results


def _ingest_plain_markdown(input_path: Path) -> list[RawDocumentData]:
    """Mode B: recursive .md scan."""
    results: list[RawDocumentData] = []
    for md_file in sorted(input_path.rglob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        frontmatter = _parse_frontmatter(content)
        rel_path = str(md_file.relative_to(input_path))
        results.append(
            RawDocumentData(
                file_path=rel_path,
                content=content,
                frontmatter=frontmatter,
            )
        )
    return results


def _parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from content if present."""
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    yaml_text = content[3:end].strip()
    result: dict = {}
    for line in yaml_text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result
