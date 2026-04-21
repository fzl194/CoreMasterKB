"""v1.1 Serving data models — ContextPack, QueryPlan, and supporting types.

Key changes from M1:
- ContextPack replaces EvidencePack as the output contract
- ContextRelation is a first-class structure, not a sub-field
- ActiveScope carries document_snapshot_map for document attribution
- QueryPlan uses generic scope dict, not fixed QueryScope fields
- source_refs_json is parsed, not passthrough
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# --- Request ---

class EntityRef(BaseModel):
    type: str = ""
    name: str
    normalized_name: str = ""


class SearchRequest(BaseModel):
    query: str
    scope: dict | None = None
    entities: list[EntityRef] | None = None
    debug: bool = False


# --- Normalized Query ---

class NormalizedQuery(BaseModel):
    original_query: str = ""
    intent: str = "general"
    entities: list[EntityRef] = Field(default_factory=list)
    scope: dict = Field(default_factory=dict)
    keywords: list[str] = Field(default_factory=list)
    desired_roles: list[str] = Field(default_factory=list)


# --- Query Plan ---

class RetrievalBudget(BaseModel):
    max_items: int = 10
    max_expanded: int = 20
    recall_multiplier: int = 5


class ExpansionConfig(BaseModel):
    enable_relation_expansion: bool = True
    max_relation_depth: int = 2
    relation_types: list[str] = Field(default_factory=lambda: [
        "previous", "next", "same_section",
        "same_parent_section", "section_header_of",
    ])


class QueryPlan(BaseModel):
    intent: str = "general"
    keywords: list[str] = Field(default_factory=list)
    entity_constraints: list[EntityRef] = Field(default_factory=list)
    scope_constraints: dict = Field(default_factory=dict)
    desired_roles: list[str] = Field(default_factory=list)
    desired_block_types: list[str] = Field(default_factory=list)
    budget: RetrievalBudget = Field(default_factory=RetrievalBudget)
    expansion: ExpansionConfig = Field(default_factory=ExpansionConfig)


# --- Retrieval ---

class RetrievalCandidate(BaseModel):
    retrieval_unit_id: str
    score: float
    source: str
    metadata: dict = Field(default_factory=dict)


# --- Active Scope ---

class ActiveScope(BaseModel):
    release_id: str
    build_id: str
    snapshot_ids: list[str] = Field(default_factory=list)
    document_snapshot_map: dict[str, str] = Field(default_factory=dict)


# --- Output ---

class ContextQuery(BaseModel):
    original: str
    normalized: str
    intent: str
    entities: list[EntityRef] = Field(default_factory=list)
    scope: dict = Field(default_factory=dict)
    keywords: list[str] = Field(default_factory=list)


class ContextItem(BaseModel):
    id: str
    kind: str
    role: str
    text: str
    score: float
    title: str | None = None
    block_type: str = "unknown"
    semantic_role: str = "unknown"
    source_id: str | None = None
    relation_to_seed: str | None = None
    source_refs: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class ContextRelation(BaseModel):
    id: str
    from_id: str
    to_id: str
    relation_type: str
    distance: int | None = None


class SourceRef(BaseModel):
    id: str
    document_key: str
    title: str | None = None
    relative_path: str | None = None
    scope_json: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class Issue(BaseModel):
    type: str
    message: str
    detail: dict = Field(default_factory=dict)


class ContextPack(BaseModel):
    query: ContextQuery
    items: list[ContextItem] = Field(default_factory=list)
    relations: list[ContextRelation] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    debug: dict | None = None
