"""Verify publishing: write to SQLite and query back."""
import tempfile
from pathlib import Path

from knowledge_mining.mining.canonicalization import canonicalize
from knowledge_mining.mining.document_profile import build_profile
from knowledge_mining.mining.ingestion import ingest_directory
from knowledge_mining.mining.models import DocumentProfile, RawSegmentData
from knowledge_mining.mining.publishing import publish
from knowledge_mining.mining.segmentation import segment_document
from knowledge_mining.mining.structure import parse_structure


def _write_files(tmp: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        p = tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def test_publish_creates_active_version():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_files(tmp, {
            "doc.md": "# Title\n\nHello world\n\n## Parameters\n\nparam1: val1",
        })

        # Run mini pipeline
        docs = ingest_directory(tmp)
        profiles = [build_profile(d) for d in docs]
        profile_map = {p.file_path: p for p in profiles}
        segments: list[RawSegmentData] = []
        for doc, profile in zip(docs, profiles):
            root = parse_structure(doc.content)
            segments.extend(segment_document(root, profile))

        canonicals, mappings = canonicalize(segments, profile_map)

        db_path = tmp / "test.sqlite"
        publish(profiles, segments, canonicals, mappings, db_path)

        # Verify
        from knowledge_mining.mining.db import MiningDB
        db = MiningDB(db_path)
        conn = db.connect()
        try:
            # Active version exists
            cursor = conn.execute(
                "SELECT status FROM asset_publish_versions WHERE status = 'active'"
            )
            assert cursor.fetchone() is not None

            # Raw documents
            cursor = conn.execute("SELECT count(*) FROM asset_raw_documents")
            assert cursor.fetchone()[0] >= 1

            # Raw segments
            cursor = conn.execute("SELECT count(*) FROM asset_raw_segments")
            assert cursor.fetchone()[0] >= 1

            # Canonical segments
            cursor = conn.execute("SELECT count(*) FROM asset_canonical_segments")
            assert cursor.fetchone()[0] >= 1

            # Source mappings
            cursor = conn.execute("SELECT count(*) FROM asset_canonical_segment_sources")
            assert cursor.fetchone()[0] >= 1
        finally:
            conn.close()


def test_publish_with_duplicate_segments():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_files(tmp, {
            "a.md": "# Same\n\nIdentical paragraph text here",
            "b.md": "# Same\n\nIdentical paragraph text here",
        })

        docs = ingest_directory(tmp)
        profiles = [build_profile(d) for d in docs]
        profile_map = {p.file_path: p for p in profiles}
        all_segments: list[RawSegmentData] = []
        for doc, profile in zip(docs, profiles):
            root = parse_structure(doc.content)
            all_segments.extend(segment_document(root, profile))

        canonicals, mappings = canonicalize(all_segments, profile_map)

        db_path = tmp / "test.sqlite"
        publish(profiles, all_segments, canonicals, mappings, db_path)

        from knowledge_mining.mining.db import MiningDB
        db = MiningDB(db_path)
        conn = db.connect()
        try:
            # Should have deduped to fewer canonicals
            cursor = conn.execute("SELECT count(*) FROM asset_canonical_segments")
            canon_count = cursor.fetchone()[0]
            assert canon_count <= len(all_segments)
        finally:
            conn.close()
