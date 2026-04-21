"""GraphExpander — SQL BFS over asset_raw_segment_relations.

Expands seed segments from source_refs_json via relation traversal.
Returns expanded segments with distance and relation type metadata.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class GraphExpander:
    """BFS graph expander for raw segment relations."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def expand(
        self,
        seed_segment_ids: list[str],
        max_depth: int = 2,
        relation_types: list[str] | None = None,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """Expand from seed segments via BFS over relations.

        Args:
            seed_segment_ids: starting segments from source_refs_json.
            max_depth: max BFS depth.
            relation_types: filter to these relation types (None = all).
            max_results: cap on total expanded segments.

        Returns:
            List of dicts with segment data + distance + relation_type.
        """
        if not seed_segment_ids:
            return []

        visited: set[str] = set(seed_segment_ids)
        current_frontier = list(seed_segment_ids)
        all_expanded: list[dict[str, Any]] = []

        for depth in range(1, max_depth + 1):
            if not current_frontier:
                break

            # Get neighbors of current frontier
            neighbors = await self._get_neighbors(
                current_frontier, relation_types,
            )

            next_frontier: list[str] = []
            for neighbor in neighbors:
                nid = str(neighbor["neighbor_id"])
                if nid in visited:
                    continue
                visited.add(nid)
                next_frontier.append(nid)

                all_expanded.append({
                    "segment_id": nid,
                    "depth": depth,
                    "relation_type": neighbor["relation_type"],
                    "from_segment_id": str(neighbor["from_id"]),
                })

                if len(all_expanded) >= max_results:
                    return all_expanded

            current_frontier = next_frontier

        return all_expanded

    async def fetch_expanded_segments(
        self,
        expansions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Fetch full segment data for expanded segment IDs."""
        if not expansions:
            return []

        segment_ids = [e["segment_id"] for e in expansions]
        expansion_map = {e["segment_id"]: e for e in expansions}

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
                ds.title AS doc_title,
                d.document_key,
                dsl.relative_path
            FROM asset_raw_segments rs
            LEFT JOIN asset_document_snapshots ds ON rs.document_snapshot_id = ds.id
            LEFT JOIN asset_document_snapshot_links dsl ON ds.id = dsl.document_snapshot_id
            LEFT JOIN asset_documents d ON dsl.document_id = d.id
            WHERE rs.id IN ({placeholders})
        """
        cursor = await self._db.execute(sql, segment_ids)
        rows = await cursor.fetchall()

        results = []
        for row in rows:
            r = dict(row)
            exp = expansion_map.get(str(r["id"]), {})
            r["expansion_depth"] = exp.get("depth", 0)
            r["expansion_relation_type"] = exp.get("relation_type", "")
            r["from_segment_id"] = exp.get("from_segment_id", "")
            results.append(r)

        return results

    async def _get_neighbors(
        self,
        segment_ids: list[str],
        relation_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get neighboring segments via relations table."""
        if not segment_ids:
            return []

        placeholders = ",".join("?" for _ in segment_ids)
        type_filter = ""
        params: list[str] = list(segment_ids) + list(segment_ids)

        if relation_types:
            type_placeholders = ",".join("?" for _ in relation_types)
            type_filter = f" AND rel.relation_type IN ({type_placeholders})"
            params.extend(relation_types)

        sql = f"""
            SELECT
                rel.source_segment_id AS from_id,
                rel.target_segment_id AS neighbor_id,
                rel.relation_type
            FROM asset_raw_segment_relations rel
            WHERE rel.source_segment_id IN ({placeholders})
            UNION ALL
            SELECT
                rel.target_segment_id AS from_id,
                rel.source_segment_id AS neighbor_id,
                rel.relation_type
            FROM asset_raw_segment_relations rel
            WHERE rel.target_segment_id IN ({placeholders})
            {type_filter}
        """
        cursor = await self._db.execute(sql, params)
        return [dict(row) for row in await cursor.fetchall()]


def parse_source_refs(source_refs_json: str | None) -> list[str]:
    """Parse source_refs_json to extract raw_segment_ids.

    source_refs_json format: {"raw_segment_ids": ["id1", "id2", ...]}
    """
    if not source_refs_json:
        return []
    try:
        data = json.loads(source_refs_json)
        if isinstance(data, dict):
            return data.get("raw_segment_ids", [])
        return []
    except (json.JSONDecodeError, TypeError):
        return []
