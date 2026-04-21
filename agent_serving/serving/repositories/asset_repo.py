"""Read-only repository for v1.1 asset_core tables.

Query path: active release → build → document snapshots → retrieval_units.
source_refs_json is parsed for content-level drill-down, not passthrough.
Relations are fetched as first-class structures.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import aiosqlite

from agent_serving.serving.schemas.models import ActiveScope, QueryPlan

logger = logging.getLogger(__name__)


class AssetRepository:
    """Read-only repo over asset_core SQLite."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def resolve_active_scope(self, channel: str = "default") -> ActiveScope:
        """Resolve active release → build → snapshots.

        Raises ValueError when:
        - 0 active releases (no data to serve)
        - >1 active releases (data integrity error)
        """
        cursor = await self._db.execute(
            "SELECT id FROM asset_publish_releases "
            "WHERE status = 'active' AND channel = ?",
            (channel,),
        )
        rows = await cursor.fetchall()

        if len(rows) == 0:
            raise ValueError("no_active_release")
        if len(rows) > 1:
            raise ValueError("multiple_active_releases")

        release_id = rows[0]["id"]

        # Get build for this release
        cursor = await self._db.execute(
            "SELECT build_id FROM asset_publish_releases WHERE id = ?",
            (release_id,),
        )
        release_row = await cursor.fetchone()
        build_id = release_row["build_id"]

        # Get document snapshots for this build
        cursor = await self._db.execute(
            "SELECT document_snapshot_id FROM asset_build_document_snapshots "
            "WHERE build_id = ?",
            (build_id,),
        )
        snapshot_rows = await cursor.fetchall()
        snapshot_ids = [r["document_snapshot_id"] for r in snapshot_rows]

        # Build document_snapshot_map: document_id → snapshot_id
        cursor = await self._db.execute(
            "SELECT bds.document_id, bds.document_snapshot_id "
            "FROM asset_build_document_snapshots bds "
            "WHERE bds.build_id = ?",
            (build_id,),
        )
        map_rows = await cursor.fetchall()
        document_snapshot_map = {r["document_id"]: r["document_snapshot_id"] for r in map_rows}

        return ActiveScope(
            release_id=release_id,
            build_id=build_id,
            snapshot_ids=snapshot_ids,
            document_snapshot_map=document_snapshot_map,
        )

    async def resolve_source_segments(
        self,
        source_refs_json: str | None,
    ) -> list[dict[str, Any]]:
        """Parse source_refs_json and fetch actual raw segments.

        This is the v1.1 drill-down: parse source_refs_json to get
        raw_segment_ids, then fetch full segment + document data.
        """
        segment_ids = self._parse_segment_ids(source_refs_json)
        if not segment_ids:
            return []

        placeholders = ",".join("?" for _ in segment_ids)
        sql = f"""
            SELECT
                rs.id,
                rs.document_snapshot_id,
                rs.raw_text,
                rs.block_type,
                rs.semantic_role,
                rs.section_path,
                rs.entity_refs_json,
                rs.source_offsets_json,
                ds.title AS snapshot_title,
                d.id AS document_id,
                d.document_key,
                dsl.relative_path
            FROM asset_raw_segments rs
            LEFT JOIN asset_document_snapshots ds ON rs.document_snapshot_id = ds.id
            LEFT JOIN asset_document_snapshot_links dsl ON ds.id = dsl.document_snapshot_id
            LEFT JOIN asset_documents d ON dsl.document_id = d.id
            WHERE rs.id IN ({placeholders})
        """
        cursor = await self._db.execute(sql, segment_ids)
        return [dict(row) for row in await cursor.fetchall()]

    async def get_relations_for_segments(
        self,
        segment_ids: list[str],
        relation_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch relations involving given segments."""
        if not segment_ids:
            return []

        placeholders = ",".join("?" for _ in segment_ids)
        params: list[str] = list(segment_ids) + list(segment_ids)

        type_filter = ""
        if relation_types:
            type_ph = ",".join("?" for _ in relation_types)
            type_filter = f" AND rel.relation_type IN ({type_ph})"
            params.extend(relation_types)

        sql = f"""
            SELECT
                rel.id,
                rel.source_segment_id AS from_segment_id,
                rel.target_segment_id AS to_segment_id,
                rel.relation_type
            FROM asset_raw_segment_relations rel
            WHERE rel.source_segment_id IN ({placeholders})
               OR rel.target_segment_id IN ({placeholders})
            {type_filter}
        """
        cursor = await self._db.execute(sql, params)
        return [dict(row) for row in await cursor.fetchall()]

    async def get_document_sources(
        self,
        document_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Fetch document metadata for source attribution."""
        if not document_ids:
            return []

        placeholders = ",".join("?" for _ in document_ids)
        sql = f"""
            SELECT
                d.id,
                d.document_key,
                dsl.relative_path,
                ds.title,
                ds.scope_json
            FROM asset_documents d
            LEFT JOIN asset_document_snapshot_links dsl ON d.id = dsl.document_id
            LEFT JOIN asset_document_snapshots ds ON dsl.document_snapshot_id = ds.id
            WHERE d.id IN ({placeholders})
        """
        cursor = await self._db.execute(sql, document_ids)
        return [dict(row) for row in await cursor.fetchall()]

    @staticmethod
    def _parse_segment_ids(source_refs_json: str | None) -> list[str]:
        """Parse source_refs_json to extract raw_segment_ids."""
        if not source_refs_json:
            return []
        try:
            data = json.loads(source_refs_json)
            if isinstance(data, dict):
                return data.get("raw_segment_ids", [])
            return []
        except (json.JSONDecodeError, TypeError):
            return []
