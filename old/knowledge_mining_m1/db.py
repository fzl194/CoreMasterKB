"""SQLite database adapter for M1 Mining — reads shared DDL, v0.5 field alignment."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4


class MiningDB:
    """SQLite dev-mode database using shared schema DDL."""

    _SHARED_SCHEMA_PATH = (
        Path(__file__).resolve().parents[2]
        / "databases"
        / "asset_core"
        / "schemas"
        / "001_asset_core.sqlite.sql"
    )

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def create_tables(self) -> None:
        schema_sql = self._SHARED_SCHEMA_PATH.read_text(encoding="utf-8")
        conn = self.connect()
        conn.executescript(schema_sql)
        conn.close()

    @staticmethod
    def create_source_batch(
        conn: sqlite3.Connection,
        batch_code: str,
        source_type: str,
        description: str | None = None,
        metadata_json: dict | None = None,
    ) -> str:
        batch_id = str(uuid4())
        conn.execute(
            """INSERT INTO asset_source_batches
               (id, batch_code, source_type, description, created_at, metadata_json)
               VALUES (?, ?, ?, ?, datetime('now'), ?)""",
            (batch_id, batch_code, source_type, description,
             json.dumps(metadata_json or {})),
        )
        return batch_id

    @staticmethod
    def create_publish_version(
        conn: sqlite3.Connection,
        version_code: str,
        status: str = "staging",
        source_batch_id: str | None = None,
        metadata_json: dict | None = None,
    ) -> str:
        pv_id = str(uuid4())
        conn.execute(
            """INSERT INTO asset_publish_versions
               (id, version_code, status, source_batch_id,
                build_started_at, metadata_json)
               VALUES (?, ?, ?, ?, datetime('now'), ?)""",
            (pv_id, version_code, status, source_batch_id,
             json.dumps(metadata_json or {})),
        )
        return pv_id

    @staticmethod
    def insert_raw_document(
        conn: sqlite3.Connection,
        publish_version_id: str,
        document_key: str,
        source_uri: str,
        relative_path: str,
        file_name: str,
        file_type: str,
        content_hash: str,
        source_type: str | None = None,
        title: str | None = None,
        document_type: str | None = None,
        scope_json: dict | None = None,
        tags_json: list | None = None,
        structure_quality: str = "unknown",
        processing_profile_json: dict | None = None,
        metadata_json: dict | None = None,
    ) -> str:
        doc_id = str(uuid4())
        conn.execute(
            """INSERT INTO asset_raw_documents
               (id, publish_version_id, document_key, source_uri, relative_path,
                file_name, file_type, content_hash, source_type, title, document_type,
                scope_json, tags_json, structure_quality,
                processing_profile_json, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (
                doc_id, publish_version_id, document_key, source_uri,
                relative_path, file_name, file_type, content_hash,
                source_type, title, document_type,
                json.dumps(scope_json or {}),
                json.dumps(tags_json or []),
                structure_quality,
                json.dumps(processing_profile_json or {}),
                json.dumps(metadata_json or {}),
            ),
        )
        return doc_id

    @staticmethod
    def insert_raw_segment(
        conn: sqlite3.Connection,
        publish_version_id: str,
        raw_document_id: str,
        segment_key: str,
        segment_index: int,
        block_type: str,
        semantic_role: str,
        raw_text: str,
        normalized_text: str,
        content_hash: str,
        normalized_hash: str,
        token_count: int | None = None,
        section_path: list | dict | None = None,
        section_title: str | None = None,
        structure_json: dict | None = None,
        source_offsets_json: dict | None = None,
        entity_refs_json: list | None = None,
        metadata_json: dict | None = None,
    ) -> str:
        seg_id = str(uuid4())
        conn.execute(
            """INSERT INTO asset_raw_segments
               (id, publish_version_id, raw_document_id, segment_key,
                segment_index, section_path, section_title, block_type, semantic_role,
                raw_text, normalized_text, content_hash, normalized_hash,
                token_count, structure_json, source_offsets_json,
                entity_refs_json, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                seg_id, publish_version_id, raw_document_id, segment_key,
                segment_index,
                json.dumps(section_path or []),
                section_title,
                block_type, semantic_role,
                raw_text, normalized_text, content_hash, normalized_hash,
                token_count,
                json.dumps(structure_json or {}),
                json.dumps(source_offsets_json or {}),
                json.dumps(entity_refs_json or []),
                json.dumps(metadata_json or {}),
            ),
        )
        return seg_id

    @staticmethod
    def insert_canonical_segment(
        conn: sqlite3.Connection,
        publish_version_id: str,
        canonical_key: str,
        block_type: str,
        semantic_role: str,
        canonical_text: str,
        search_text: str,
        title: str | None = None,
        summary: str | None = None,
        entity_refs_json: list | None = None,
        scope_json: dict | None = None,
        has_variants: bool = False,
        variant_policy: str = "none",
        quality_score: float | None = None,
        metadata_json: dict | None = None,
    ) -> str:
        canon_id = str(uuid4())
        conn.execute(
            """INSERT INTO asset_canonical_segments
               (id, publish_version_id, canonical_key, block_type, semantic_role,
                title, canonical_text, summary, search_text,
                entity_refs_json, scope_json, has_variants, variant_policy,
                quality_score, created_at, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)""",
            (
                canon_id, publish_version_id, canonical_key,
                block_type, semantic_role,
                title, canonical_text, summary, search_text,
                json.dumps(entity_refs_json or []),
                json.dumps(scope_json or {}),
                1 if has_variants else 0, variant_policy,
                quality_score,
                json.dumps(metadata_json or {}),
            ),
        )
        return canon_id

    @staticmethod
    def insert_source_mapping(
        conn: sqlite3.Connection,
        publish_version_id: str,
        canonical_segment_id: str,
        raw_segment_id: str,
        relation_type: str,
        is_primary: bool = False,
        priority: int = 100,
        similarity_score: float | None = None,
        diff_summary: str | None = None,
        metadata_json: dict | None = None,
    ) -> str:
        mapping_id = str(uuid4())
        conn.execute(
            """INSERT INTO asset_canonical_segment_sources
               (id, publish_version_id, canonical_segment_id, raw_segment_id,
                relation_type, is_primary, priority, similarity_score,
                diff_summary, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mapping_id, publish_version_id,
                canonical_segment_id, raw_segment_id,
                relation_type, 1 if is_primary else 0, priority,
                similarity_score, diff_summary,
                json.dumps(metadata_json or {}),
            ),
        )
        return mapping_id

    @staticmethod
    def activate_version(conn: sqlite3.Connection, new_pv_id: str) -> None:
        """Atomically: archive old active, activate new staging."""
        conn.execute(
            "UPDATE asset_publish_versions SET status = 'archived' WHERE status = 'active'",
        )
        conn.execute(
            """UPDATE asset_publish_versions
               SET status = 'active', activated_at = datetime('now')
               WHERE id = ?""",
            (new_pv_id,),
        )

    @staticmethod
    def fail_version(conn: sqlite3.Connection, pv_id: str, error: str) -> None:
        """Mark version as failed, do not affect existing active."""
        conn.execute(
            """UPDATE asset_publish_versions
               SET status = 'failed', build_finished_at = datetime('now'),
                   build_error = ?
               WHERE id = ?""",
            (error, pv_id),
        )
