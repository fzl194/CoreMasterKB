"""EvidenceAssembler — build EvidencePack from query results.

Separates evidence, variants, conflicts, and gaps.
Uses v0.5 field names (block_type, semantic_role, entity_refs_json, scope_json).
"""
from __future__ import annotations

import json

from agent_serving.serving.schemas.models import (
    CanonicalItem,
    ConflictInfo,
    EntityRef,
    EvidenceItem,
    EvidencePack,
    Gap,
    NormalizedQuery,
    QueryPlan,
    QueryScope,
    SourceRef,
    UnparsedDocument,
    VariantInfo,
)


class EvidenceAssembler:
    def assemble(
        self,
        *,
        query: str,
        intent: str,
        normalized: NormalizedQuery,
        plan: QueryPlan,
        canonical_hits: list[dict],
        drill_results: list[tuple[list[dict], list[dict], list[dict]]],
        unparsed_docs: list[dict] | None = None,
    ) -> EvidencePack:
        """Assemble EvidencePack from drill-down results.

        drill_results is a list of (evidence, variants, conflicts) tuples,
        one per canonical hit.
        unparsed_docs: documents registered but not parsed into segments.
        """
        # Build canonical items
        canonical_items = [
            self._build_canonical_item(h) for h in canonical_hits
        ]

        # Build evidence, variants, conflicts, sources from drill results
        all_evidence: list[dict] = []
        all_variants: list[dict] = []
        all_conflicts: list[dict] = []

        for evidence_rows, variant_rows, conflict_rows in drill_results:
            all_evidence.extend(evidence_rows)
            all_variants.extend(variant_rows)
            all_conflicts.extend(conflict_rows)

        evidence_items = [self._build_evidence_item(r) for r in all_evidence]
        sources = [self._build_source(r) for r in all_evidence]
        variants = [self._build_variant(r) for r in all_variants]
        conflicts = [self._build_conflict(r) for r in all_conflicts]

        # Build gaps
        gaps = self._build_gaps(normalized, canonical_hits, all_variants)

        # Matched entities and scope from canonical hits
        matched_entities = self._collect_entities(canonical_hits)
        matched_scope = self._collect_scope(canonical_hits)

        # Build followups
        followups = self._build_followups(gaps, conflicts)

        # Build unparsed documents
        unparsed_items = self._build_unparsed_docs(unparsed_docs or [])

        return EvidencePack(
            query=query,
            intent=intent,
            normalized_query=self._build_normalized_str(normalized),
            query_plan=plan,
            canonical_items=canonical_items,
            evidence_items=evidence_items,
            sources=sources,
            matched_entities=matched_entities,
            matched_scope=matched_scope,
            variants=variants,
            conflicts=conflicts,
            gaps=gaps,
            suggested_followups=followups,
            unparsed_documents=unparsed_items,
        )

    def _build_canonical_item(self, h: dict) -> CanonicalItem:
        entity_refs = _parse_entity_refs(h.get("entity_refs_json", "[]"))
        scope = _parse_scope(h.get("scope_json", "{}"))

        return CanonicalItem(
            id=str(h["id"]),
            canonical_key=h.get("canonical_key", ""),
            block_type=h.get("block_type", "unknown"),
            semantic_role=h.get("semantic_role", "unknown"),
            title=h.get("title"),
            canonical_text=h["canonical_text"],
            summary=h.get("summary"),
            entity_refs=entity_refs,
            scope=scope,
            has_variants=bool(h.get("has_variants")),
            variant_policy=h.get("variant_policy", "none"),
            quality_score=h.get("quality_score"),
        )

    def _build_evidence_item(self, r: dict) -> EvidenceItem:
        entity_refs = _parse_entity_refs(r.get("entity_refs_json", "[]"))
        structure = _parse_json_dict(r.get("structure_json", "{}"))
        source_offsets = _parse_json_dict(r.get("source_offsets_json", "{}"))

        return EvidenceItem(
            id=str(r["id"]),
            block_type=r.get("block_type", "unknown"),
            semantic_role=r.get("semantic_role", "unknown"),
            raw_text=r["raw_text"],
            section_path=_parse_section_path(r.get("section_path", "[]")),
            section_title=r.get("section_title"),
            entity_refs=entity_refs,
            structure=structure,
            source_offsets=source_offsets,
        )

    def _build_source(self, r: dict) -> SourceRef:
        scope = _parse_scope(r.get("doc_scope_json", "{}"))
        tags = _parse_json_list(r.get("tags_json", "[]"))

        return SourceRef(
            document_key=r.get("document_key", ""),
            relative_path=r.get("relative_path"),
            section_path=_parse_section_path(r.get("section_path", "[]")),
            block_type=r.get("block_type"),
            scope=scope,
            file_type=r.get("file_type"),
            document_type=r.get("document_type"),
            tags=tags,
        )

    def _build_variant(self, r: dict) -> VariantInfo:
        scope = _parse_scope(r.get("doc_scope_json", "{}"))

        return VariantInfo(
            raw_segment_id=str(r["id"]),
            relation_type=r.get("relation_type", "scope_variant"),
            diff_summary=r.get("diff_summary"),
            scope=scope,
        )

    def _build_conflict(self, r: dict) -> ConflictInfo:
        scope = _parse_scope(r.get("doc_scope_json", "{}"))
        entity_refs = _parse_entity_refs(r.get("entity_refs_json", "[]"))
        source = SourceRef(
            document_key=r.get("document_key", ""),
            relative_path=r.get("relative_path"),
            section_path=_parse_section_path(r.get("section_path", "[]")),
            scope=scope,
            file_type=r.get("file_type"),
            document_type=r.get("document_type"),
        )

        return ConflictInfo(
            raw_segment_id=str(r.get("id", "")) or None,
            relation_type=r.get("relation_type"),
            raw_text=r.get("raw_text", ""),
            diff_summary=r.get("diff_summary"),
            scope=scope,
            entity_refs=entity_refs,
            source=source,
            section_path=_parse_section_path(r.get("section_path", "[]")),
        )

    def _build_gaps(
        self, normalized: NormalizedQuery, hits: list[dict], variants: list[dict],
    ) -> list[Gap]:
        gaps: list[Gap] = []
        has_variants_hit = any(h.get("has_variants") for h in hits)

        if has_variants_hit and normalized.missing_constraints:
            if "product" in normalized.missing_constraints:
                # Derive product options from actual variant scopes, not hardcoded list
                product_options = sorted({
                    p
                    for v in variants
                    for p in _parse_scope(v.get("doc_scope_json", "{}")).products
                }) if variants else []
                gaps.append(Gap(
                    field="product",
                    reason="该知识在不同产品上有差异，需要指定产品",
                    suggested_options=product_options,
                ))
            if "product_version" in normalized.missing_constraints:
                gaps.append(Gap(
                    field="product_version",
                    reason="该知识在不同版本间可能有差异",
                    suggested_options=[],
                ))

        if variants:
            scope_descs = []
            for v in variants[-3:]:
                scope = v.get("doc_scope_json", "{}")
                scope_descs.append(str(scope))
            gaps.append(Gap(
                field="scope_variant",
                reason=f"存在 {len(variants)} 个 scope 变体未纳入主 evidence",
                suggested_options=[],
            ))

        return gaps

    def _collect_entities(self, hits: list[dict]) -> list[EntityRef]:
        seen: set[str] = set()
        result: list[EntityRef] = []
        for h in hits:
            refs = _parse_entity_refs(h.get("entity_refs_json", "[]"))
            for ref in refs:
                key = f"{ref.type}:{ref.normalized_name}"
                if key not in seen:
                    result.append(ref)
                    seen.add(key)
        return result

    def _collect_scope(self, hits: list[dict]) -> QueryScope:
        all_products: list[str] = []
        all_versions: list[str] = []
        all_nes: list[str] = []
        all_projects: list[str] = []
        all_domains: list[str] = []

        for h in hits:
            scope = _parse_scope(h.get("scope_json", "{}"))
            for p in scope.products:
                if p not in all_products:
                    all_products.append(p)
            for v in scope.product_versions:
                if v not in all_versions:
                    all_versions.append(v)
            for ne in scope.network_elements:
                if ne not in all_nes:
                    all_nes.append(ne)
            for pr in scope.projects:
                if pr not in all_projects:
                    all_projects.append(pr)
            for d in scope.domains:
                if d not in all_domains:
                    all_domains.append(d)

        return QueryScope(
            products=all_products,
            product_versions=all_versions,
            network_elements=all_nes,
            projects=all_projects,
            domains=all_domains,
        )

    def _build_followups(self, gaps: list[Gap], conflicts: list[ConflictInfo]) -> list[str]:
        parts: list[str] = []
        gap_fields = [g.field for g in gaps if g.field != "scope_variant"]
        if gap_fields:
            parts.append(f"请确认{'/'.join(gap_fields)}以获取精确答案")
        if conflicts:
            parts.append(f"发现 {len(conflicts)} 处知识冲突，建议核实产品版本后重新查询")
        if any(g.field == "scope_variant" for g in gaps):
            parts.append("部分 scope 变体未展示，可指定更精确的产品/版本/网元缩小范围")
        return parts

    def _build_normalized_str(self, normalized: NormalizedQuery) -> str:
        parts: list[str] = []
        parts.append(f"intent={normalized.intent}")
        for e in normalized.entities:
            parts.append(f"{e.type}={e.name}")
        if normalized.scope.products:
            parts.append(f"products={','.join(normalized.scope.products)}")
        if normalized.scope.product_versions:
            parts.append(f"versions={','.join(normalized.scope.product_versions)}")
        if normalized.scope.network_elements:
            parts.append(f"nes={','.join(normalized.scope.network_elements)}")
        parts.extend(normalized.keywords)
        return " ".join(parts)

    def _build_unparsed_docs(self, raw_docs: list[dict]) -> list[UnparsedDocument]:
        items: list[UnparsedDocument] = []
        for doc in raw_docs:
            scope = _parse_scope(doc.get("scope_json", "{}"))
            items.append(UnparsedDocument(
                id=str(doc["id"]),
                document_key=doc.get("document_key", ""),
                relative_path=doc.get("relative_path"),
                file_type=doc.get("file_type"),
                document_type=doc.get("document_type"),
                scope=scope,
            ))
        return items


# --- JSON helpers ---

def _parse_json_dict(raw: str | dict) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _parse_json_list(raw: str | list) -> list[str]:
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_section_path(raw: str | list) -> list[str]:
    if isinstance(raw, list):
        if raw and isinstance(raw[0], dict):
            return [item.get("title", "") for item in raw if item.get("title")]
        return raw
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            if parsed and isinstance(parsed[0], dict):
                return [item.get("title", "") for item in parsed if item.get("title")]
            return parsed
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_entity_refs(raw: str | list) -> list[EntityRef]:
    if isinstance(raw, list):
        items = raw
    else:
        try:
            items = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    return [
        EntityRef(
            type=item.get("type", "unknown"),
            name=item.get("name", ""),
            normalized_name=item.get("normalized_name", item.get("name", "")),
        )
        for item in items
        if isinstance(item, dict)
    ]


def _parse_scope(raw: str | dict) -> QueryScope:
    if isinstance(raw, dict):
        d = raw
    else:
        try:
            d = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return QueryScope()
    if not isinstance(d, dict):
        return QueryScope()

    def _get_list(key: str) -> list[str]:
        val = d.get(key)
        if val is None:
            # Try singular fallback
            singular = key.rstrip("s")
            val = d.get(singular)
        if val is None:
            return []
        if isinstance(val, str):
            return [val]
        if isinstance(val, list):
            return val
        return []

    return QueryScope(
        products=_get_list("products"),
        product_versions=_get_list("product_versions"),
        network_elements=_get_list("network_elements"),
        projects=_get_list("projects"),
        domains=_get_list("domains"),
    )
