"""Pydantic models for generic evidence retrieval.

v0.5 schema uses entity_refs_json / scope_json / block_type / semantic_role
instead of command-centric fixed fields. Models below reflect this.

JSON tolerance: all JSON-derived fields default to empty — missing data
doesn't block retrieval, only affects filtering/sorting.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# --- Request ---

class SearchRequest(BaseModel):
    query: str
    scope: QueryScope | None = None  # forward ref resolved below
    entities: list[EntityRef] | None = None
    debug: bool = False


class CommandUsageRequest(BaseModel):
    query: str


# --- Normalized Query ---

class EntityRef(BaseModel):
    """A single entity extracted from the query."""
    type: str = ""  # command, feature, term, alarm, network_element, etc.
    name: str
    normalized_name: str = ""


class QueryScope(BaseModel):
    """Scope constraints extracted from the query."""
    products: list[str] = Field(default_factory=list)
    product_versions: list[str] = Field(default_factory=list)
    network_elements: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    scenarios: list[str] = Field(default_factory=list)
    authors: list[str] = Field(default_factory=list)


class NormalizedQuery(BaseModel):
    intent: str = "general"
    entities: list[EntityRef] = Field(default_factory=list)
    scope: QueryScope = Field(default_factory=QueryScope)
    keywords: list[str] = Field(default_factory=list)
    desired_semantic_roles: list[str] = Field(default_factory=list)
    desired_block_types: list[str] = Field(default_factory=list)
    missing_constraints: list[str] = Field(default_factory=list)


# --- QueryPlan ---

class EvidenceBudget(BaseModel):
    canonical_limit: int = 10
    raw_per_canonical: int = 3


class ExpansionConfig(BaseModel):
    use_ontology: bool = False
    max_hops: int = 0


class QueryPlan(BaseModel):
    """Stable intermediate plan between understanding and execution."""
    intent: str = "general"
    retrieval_targets: list[str] = Field(default_factory=lambda: ["canonical_segments"])
    entity_constraints: list[EntityRef] = Field(default_factory=list)
    scope_constraints: QueryScope = Field(default_factory=QueryScope)
    semantic_role_preferences: list[str] = Field(default_factory=list)
    block_type_preferences: list[str] = Field(default_factory=list)
    variant_policy: str = "flag"
    conflict_policy: str = "flag_not_answer"
    evidence_budget: EvidenceBudget = Field(default_factory=EvidenceBudget)
    expansion: ExpansionConfig = Field(default_factory=ExpansionConfig)
    keywords: list[str] = Field(default_factory=list)


# --- Response ---

class CanonicalItem(BaseModel):
    id: str
    canonical_key: str
    block_type: str
    semantic_role: str
    title: str | None = None
    canonical_text: str
    summary: str | None = None
    entity_refs: list[EntityRef] = Field(default_factory=list)
    scope: QueryScope = Field(default_factory=QueryScope)
    has_variants: bool = False
    variant_policy: str = "none"
    quality_score: float | None = None


class EvidenceItem(BaseModel):
    id: str
    block_type: str
    semantic_role: str
    raw_text: str
    section_path: list[str] = Field(default_factory=list)
    section_title: str | None = None
    entity_refs: list[EntityRef] = Field(default_factory=list)
    structure: dict = Field(default_factory=dict)
    source_offsets: dict = Field(default_factory=dict)


class SourceRef(BaseModel):
    document_key: str
    relative_path: str | None = None
    section_path: list[str] = Field(default_factory=list)
    block_type: str | None = None
    scope: QueryScope = Field(default_factory=QueryScope)
    file_type: str | None = None
    document_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    processing_profile: dict = Field(default_factory=dict)


class VariantInfo(BaseModel):
    raw_segment_id: str
    relation_type: str
    diff_summary: str | None = None
    scope: QueryScope = Field(default_factory=QueryScope)


class ConflictInfo(BaseModel):
    raw_segment_id: str | None = None
    relation_type: str | None = None
    raw_text: str
    diff_summary: str | None = None
    scope: QueryScope = Field(default_factory=QueryScope)
    entity_refs: list[EntityRef] = Field(default_factory=list)
    source: SourceRef | None = None
    section_path: list[str] = Field(default_factory=list)


class UnparsedDocument(BaseModel):
    id: str
    document_key: str
    relative_path: str | None = None
    file_type: str | None = None
    document_type: str | None = None
    scope: QueryScope = Field(default_factory=QueryScope)
    tags: list[str] = Field(default_factory=list)
    processing_profile: dict = Field(default_factory=dict)


class Gap(BaseModel):
    field: str
    reason: str
    suggested_options: list[str] = Field(default_factory=list)


class EvidencePack(BaseModel):
    query: str
    intent: str
    normalized_query: str
    query_plan: QueryPlan | None = None
    canonical_items: list[CanonicalItem] = Field(default_factory=list)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    matched_entities: list[EntityRef] = Field(default_factory=list)
    matched_scope: QueryScope = Field(default_factory=QueryScope)
    variants: list[VariantInfo] = Field(default_factory=list)
    conflicts: list[ConflictInfo] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    unparsed_documents: list[UnparsedDocument] = Field(default_factory=list)
    debug_trace: dict | None = None


# Fix forward references
SearchRequest.model_rebuild()
