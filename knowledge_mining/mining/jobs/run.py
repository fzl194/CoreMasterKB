"""Pipeline entry point: orchestrate all mining modules."""
from __future__ import annotations

import argparse
from pathlib import Path

from knowledge_mining.mining.canonicalization import canonicalize
from knowledge_mining.mining.document_profile import build_profile
from knowledge_mining.mining.ingestion import ingest_directory
from knowledge_mining.mining.models import DocumentProfile, RawSegmentData
from knowledge_mining.mining.publishing import publish
from knowledge_mining.mining.segmentation import segment_document
from knowledge_mining.mining.structure import parse_structure


def run_pipeline(input_path: Path, db_path: Path) -> dict:
    """Run the full mining pipeline: ingest → profile → structure → segment → canonicalize → publish.

    Returns a summary dict with counts.
    """
    # Step 1: Ingest
    docs = ingest_directory(input_path)
    if not docs:
        return {"documents": 0, "segments": 0, "canonicals": 0, "mappings": 0}

    # Step 2: Profile
    profiles = [build_profile(d) for d in docs]
    profile_map = {p.file_path: p for p in profiles}

    # Step 3: Structure + Segment
    all_segments: list[RawSegmentData] = []
    for doc, profile in zip(docs, profiles):
        root = parse_structure(doc.content)
        segments = segment_document(root, profile)
        all_segments.extend(segments)

    # Step 4: Canonicalize
    canonicals, mappings = canonicalize(all_segments, profile_map)

    # Step 5: Publish
    source_type = "folder_scan"
    if docs[0].manifest_meta:
        source_type = docs[0].manifest_meta.get("source_type", "folder_scan")

    publish(
        profiles, all_segments, canonicals, mappings,
        db_path=db_path,
        version_code="v1",
        batch_code="batch-001",
        source_type=source_type,
    )

    return {
        "documents": len(docs),
        "segments": len(all_segments),
        "canonicals": len(canonicals),
        "mappings": len(mappings),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="M1 Knowledge Mining Pipeline")
    parser.add_argument("--input", required=True, help="Input directory path")
    parser.add_argument("--db", required=True, help="Output SQLite database path")
    args = parser.parse_args()

    summary = run_pipeline(Path(args.input), Path(args.db))
    print(f"Pipeline complete: {summary}")


if __name__ == "__main__":
    main()
