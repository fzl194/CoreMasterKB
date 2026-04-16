"""Publishing module: write pipeline results to SQLite via shared DDL."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from knowledge_mining.mining.db import MiningDB
from knowledge_mining.mining.models import (
    CanonicalSegmentData,
    DocumentProfile,
    RawSegmentData,
    SourceMappingData,
)
from knowledge_mining.mining.text_utils import content_hash


def publish(
    profiles: list[DocumentProfile],
    segments: list[RawSegmentData],
    canonicals: list[CanonicalSegmentData],
    source_mappings: list[SourceMappingData],
    db_path: Path,
    version_code: str = "v1",
    batch_code: str = "batch-001",
    source_type: str = "folder_scan",
) -> None:
    """Write all pipeline results to SQLite."""
    db = MiningDB(db_path)
    db.create_tables()
    conn = db.connect()
    try:
        batch_id = db.create_source_batch(conn, batch_code, source_type)
        pv_id = db.create_publish_version(
            conn, version_code=version_code, status="staging",
            source_batch_id=batch_id,
        )

        # Insert raw documents
        doc_ids: dict[str, str] = {}
        for profile in profiles:
            doc_id = db.insert_raw_document(
                conn,
                publish_version_id=pv_id,
                document_key=profile.file_path,
                source_uri=profile.file_path,
                file_name=Path(profile.file_path).name,
                file_type="markdown",
                content_hash=content_hash(profile.file_path),
                source_type=profile.source_type,
                scope_json=profile.scope_json,
                tags_json=profile.tags_json,
                structure_quality=profile.structure_quality,
            )
            doc_ids[profile.file_path] = doc_id

        # Insert raw segments
        seg_ids: dict[str, str] = {}
        for seg in segments:
            seg_key = f"{seg.document_file_path}#{seg.segment_index}"
            seg_id = db.insert_raw_segment(
                conn,
                publish_version_id=pv_id,
                raw_document_id=doc_ids.get(seg.document_file_path, ""),
                segment_key=seg_key,
                segment_index=seg.segment_index,
                segment_type=seg.segment_type,
                block_type=seg.block_type,
                raw_text=seg.raw_text,
                normalized_text=seg.normalized_text,
                content_hash=seg.content_hash,
                normalized_hash=seg.normalized_hash,
                section_path=seg.section_path,
                section_title=seg.section_title,
                heading_level=seg.heading_level,
                section_role=seg.section_role,
                command_name=seg.command_name,
                token_count=seg.token_count,
                structure_json=seg.structure_json,
                source_offsets_json=seg.source_offsets_json,
            )
            seg_ids[seg_key] = seg_id

        # Insert canonical segments
        canon_ids: dict[str, str] = {}
        for canon in canonicals:
            canon_id = str(uuid4())
            conn.execute(
                """INSERT INTO asset_canonical_segments
                   (id, publish_version_id, canonical_key, segment_type, section_role,
                    title, command_name, canonical_text, search_text,
                    has_variants, variant_policy, created_at, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), '{}')""",
                (
                    canon_id, pv_id, canon.canonical_key, canon.segment_type,
                    canon.section_role, canon.title, canon.command_name,
                    canon.canonical_text, canon.search_text,
                    1 if canon.has_variants else 0, canon.variant_policy,
                ),
            )
            canon_ids[canon.canonical_key] = canon_id

        # Insert source mappings
        for mapping in source_mappings:
            conn.execute(
                """INSERT INTO asset_canonical_segment_sources
                   (id, publish_version_id, canonical_segment_id, raw_segment_id,
                    relation_type, is_primary, priority, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, 100, '{}')""",
                (
                    str(uuid4()), pv_id,
                    canon_ids.get(mapping.canonical_key, ""),
                    seg_ids.get(mapping.raw_segment_ref, ""),
                    mapping.relation_type,
                    1 if mapping.relation_type == "primary" else 0,
                ),
            )

        conn.commit()

        # Activate
        conn.execute(
            "UPDATE asset_publish_versions SET status = 'active', activated_at = datetime('now') WHERE id = ?",
            (pv_id,),
        )
        conn.commit()
    finally:
        conn.close()
