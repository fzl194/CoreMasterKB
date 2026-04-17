"""Read-only repository for asset tables (L0/L1/L2).

All queries enforce publish_version_id = active version per schema README.
Uses QueryPlan for search — no command-specific SQL paths.

JSON tolerance principles:
- scope_json: compatible with singular (product) and plural (products)
- entity_refs_json: fallback to name when normalized_name missing
- Missing JSON fields don't block retrieval, only affect filtering/sorting
"""
from __future__ import annotations

import json
from typing import Any

import aiosqlite

from agent_serving.serving.schemas.models import QueryPlan, QueryScope


class AssetRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get_active_publish_version_id(self) -> tuple[str | None, str | None]:
        """Get active publish version ID with validation.

        Returns (pv_id, error_message).
        - (id, None) — exactly 1 active
        - (None, "no_active_version") — 0 active
        - (None, "multiple_active_versions") — >1 active (data integrity issue)
        """
        cursor = await self._db.execute(
            "SELECT id FROM asset_publish_versions WHERE status = 'active'"
        )
        rows = await cursor.fetchall()
        if len(rows) == 0:
            return None, "no_active_version"
        if len(rows) > 1:
            return None, "multiple_active_versions"
        return rows[0]["id"], None

    async def get_unparsed_documents(
        self, pv_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get documents registered but not parsed into segments."""
        if pv_id is None:
            pv_id, _ = await self.get_active_publish_version_id()
        if pv_id is None:
            return []

        cursor = await self._db.execute(
            "SELECT rd.id, rd.document_key, rd.relative_path, rd.file_type, "
            "  rd.document_type, rd.scope_json, rd.tags_json "
            "FROM asset_raw_documents rd "
            "WHERE rd.publish_version_id = ? "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM asset_raw_segments rs WHERE rs.raw_document_id = rd.id"
            ")",
            (pv_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def search_canonical(
        self, plan: QueryPlan, pv_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search canonical segments based on QueryPlan.

        Strategy: search_text LIKE recall, then Python-side JSON filtering.
        Falls back to canonical_text/title when entity_refs is empty.
        """
        if pv_id is None:
            pv_id, _ = await self.get_active_publish_version_id()
        if pv_id is None:
            return []

        conditions = ["cs.publish_version_id = ?"]
        params: list[Any] = [pv_id]

        # Entity name search via search_text
        entity_names = [e.name for e in plan.entity_constraints]
        if entity_names:
            like_clauses = " OR ".join("cs.search_text LIKE ?" for _ in entity_names)
            conditions.append(f"({like_clauses})")
            params.extend(f"%{self._escape_like(name)}%" for name in entity_names)
        elif plan.keywords:
            like_clauses = " OR ".join("cs.search_text LIKE ?" for _ in plan.keywords)
            conditions.append(f"({like_clauses})")
            params.extend(f"%{self._escape_like(kw)}%" for kw in plan.keywords)
        else:
            return []

        query = f"SELECT * FROM asset_canonical_segments cs WHERE {' AND '.join(conditions)}"
        query += " LIMIT ?"
        params.append(plan.evidence_budget.canonical_limit)

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        results = [dict(row) for row in rows]

        # Python-side JSON filtering — only when entity_refs has data
        if plan.entity_constraints:
            entity_filtered = self._filter_by_entities(results, plan.entity_constraints)
            # If entity filtering drops everything, fall back to text-only results
            if entity_filtered:
                results = entity_filtered

        if plan.semantic_role_preferences:
            results = self._sort_by_semantic_roles(results, plan.semantic_role_preferences)

        if plan.block_type_preferences:
            results = self._sort_by_block_types(results, plan.block_type_preferences)

        return results

    async def drill_down(
        self,
        canonical_segment_id: str,
        plan: QueryPlan,
        pv_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Drill down from canonical to raw evidence.

        Returns (evidence_rows, variant_rows, conflict_rows) separately.
        scope_variant: only enters evidence when scope is sufficient AND matches.
        conflict_candidate: always goes to conflicts, never evidence.
        """
        if pv_id is None:
            pv_id, _ = await self.get_active_publish_version_id()
        if pv_id is None:
            return [], [], []

        query = (
            "SELECT rs.id, rs.block_type, rs.semantic_role, rs.raw_text, "
            "  rs.section_path, rs.section_title, rs.entity_refs_json, "
            "  rs.structure_json, rs.source_offsets_json, "
            "  rd.document_key, rd.relative_path, rd.file_type, "
            "  rd.document_type, rd.scope_json AS doc_scope_json, "
            "  rd.tags_json, rd.processing_profile_json, "
            "  csources.relation_type, csources.diff_summary, "
            "  csources.metadata_json AS source_metadata "
            "FROM asset_canonical_segment_sources csources "
            "JOIN asset_raw_segments rs ON csources.raw_segment_id = rs.id "
            "JOIN asset_raw_documents rd ON rs.raw_document_id = rd.id "
            "WHERE csources.canonical_segment_id = ? "
            "AND csources.publish_version_id = ? "
            "ORDER BY csources.is_primary DESC, csources.priority ASC"
        )
        cursor = await self._db.execute(query, (canonical_segment_id, pv_id))
        rows = await cursor.fetchall()

        evidence: list[dict[str, Any]] = []
        variants: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []

        scope_sufficient = self._scope_is_sufficient(plan.scope_constraints)

        for row in rows:
            r = dict(row)
            rel_type = r["relation_type"]

            if rel_type == "conflict_candidate":
                conflicts.append(r)
            elif rel_type == "scope_variant":
                if scope_sufficient and self._matches_scope(r, plan.scope_constraints):
                    evidence.append(r)
                else:
                    variants.append(r)
            else:
                # primary, exact_duplicate, normalized_duplicate, near_duplicate
                if self._matches_scope(r, plan.scope_constraints):
                    evidence.append(r)
                else:
                    variants.append(r)

        limit = plan.evidence_budget.raw_per_canonical
        if len(evidence) > limit:
            evidence = evidence[:limit]

        return evidence, variants, conflicts

    async def get_conflict_sources(
        self, canonical_segment_id: str, pv_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get conflict candidates for a canonical segment."""
        if pv_id is None:
            pv_id, _ = await self.get_active_publish_version_id()
        if pv_id is None:
            return []

        cursor = await self._db.execute(
            "SELECT rs.id, rs.raw_text, rs.entity_refs_json, "
            "  rs.section_path, rs.section_title, "
            "  rd.document_key, rd.relative_path, rd.scope_json AS doc_scope_json, "
            "  csources.relation_type, csources.diff_summary "
            "FROM asset_canonical_segment_sources csources "
            "JOIN asset_raw_segments rs ON csources.raw_segment_id = rs.id "
            "JOIN asset_raw_documents rd ON rs.raw_document_id = rd.id "
            "WHERE csources.canonical_segment_id = ? "
            "AND csources.publish_version_id = ? "
            "AND csources.relation_type = 'conflict_candidate'",
            (canonical_segment_id, pv_id),
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- Private helpers ---

    @staticmethod
    def _escape_like(value: str) -> str:
        """Escape LIKE special characters (%, _) in user-controlled values."""
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def _filter_by_entities(
        self, results: list[dict], entity_constraints: list,
    ) -> list[dict]:
        """Filter canonical results by entity_refs_json match.

        Falls back to name comparison when normalized_name is missing.
        Returns empty list if no entity_refs match — caller decides whether
        to use text-only fallback.
        """
        if not entity_constraints:
            return results

        filtered = []
        for r in results:
            try:
                refs = json.loads(r.get("entity_refs_json", "[]"))
            except (json.JSONDecodeError, TypeError):
                refs = []

            if not refs:
                # entity_refs empty — can't filter, skip this result
                continue

            for constraint in entity_constraints:
                matched = False
                for ref in refs:
                    # Type match
                    ref_type = ref.get("type", "")
                    if ref_type and ref_type != constraint.type:
                        continue
                    # Name match: prefer normalized_name, fallback to name
                    ref_name = (ref.get("normalized_name") or ref.get("name", "")).lower()
                    constraint_name = (constraint.normalized_name or constraint.name).lower()
                    if ref_name == constraint_name:
                        matched = True
                        break
                if matched:
                    filtered.append(r)
                    break

        return filtered

    def _sort_by_semantic_roles(
        self, results: list[dict], preferred_roles: list[str],
    ) -> list[dict]:
        """Prefer results matching desired semantic roles, don't exclude others."""
        if not preferred_roles:
            return results
        preferred = [r for r in results if r.get("semantic_role", "unknown") in preferred_roles]
        other = [r for r in results if r.get("semantic_role", "unknown") not in preferred_roles]
        return preferred + other

    def _sort_by_block_types(
        self, results: list[dict], preferred_types: list[str],
    ) -> list[dict]:
        """Prefer results matching desired block types, don't exclude others."""
        if not preferred_types:
            return results
        preferred = [r for r in results if r.get("block_type", "unknown") in preferred_types]
        other = [r for r in results if r.get("block_type", "unknown") not in preferred_types]
        return preferred + other

    def _scope_is_sufficient(self, scope: QueryScope) -> bool:
        """Check if query provides enough scope to resolve variants.

        At minimum: products must be specified for scope_variant resolution.
        """
        return bool(scope.products)

    def _matches_scope(self, row: dict, scope: QueryScope) -> bool:
        """Check if a raw evidence row matches scope constraints.

        Compatible with singular/plural scope_json.
        If no scope constraints specified, everything matches.
        """
        # Check all scope dimensions — if any is constrained, it must match
        scope_dims = [
            ("products", scope.products),
            ("product_versions", scope.product_versions),
            ("network_elements", scope.network_elements),
            ("projects", scope.projects),
            ("domains", scope.domains),
        ]
        has_any_constraint = any(v for _, v in scope_dims)
        if not has_any_constraint:
            return True

        try:
            doc_scope = json.loads(row.get("doc_scope_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            doc_scope = {}

        for plural_key, constraint_values in scope_dims:
            if not constraint_values:
                continue
            # Try plural first, then singular
            doc_values = doc_scope.get(plural_key)
            if doc_values is None:
                singular = plural_key.rstrip("s")
                doc_values = doc_scope.get(singular)
                if doc_values is None:
                    # Also try singular without 's' (e.g., scenario -> scenarios)
                    continue
            # Normalize to list
            if isinstance(doc_values, str):
                doc_values = [doc_values]
            elif not isinstance(doc_values, list):
                continue
            if not any(v in doc_values for v in constraint_values):
                return False

        return True
