"""Pydantic models for Agent Serving request/response."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str


class CommandUsageRequest(BaseModel):
    query: str


class KeyObjects(BaseModel):
    command: str | None = None
    product: str | None = None
    product_version: str | None = None
    network_element: str | None = None


class NormalizedQuery(BaseModel):
    command: str | None = None
    product: str | None = None
    product_version: str | None = None
    network_element: str | None = None
    keywords: list[str] = Field(default_factory=list)
    missing_constraints: list[str] = Field(default_factory=list)


class CanonicalSegmentRef(BaseModel):
    id: str
    segment_type: str
    title: str | None = None
    canonical_text: str
    command_name: str | None = None
    has_variants: bool = False
    variant_policy: str = "none"


class RawSegmentRef(BaseModel):
    id: str
    segment_type: str
    raw_text: str
    command_name: str | None = None
    section_path: list[str] = Field(default_factory=list)
    section_title: str | None = None


class AnswerMaterials(BaseModel):
    canonical_segments: list[CanonicalSegmentRef] = Field(default_factory=list)
    raw_segments: list[RawSegmentRef] = Field(default_factory=list)


class SourceRef(BaseModel):
    document_key: str
    section_path: list[str] = Field(default_factory=list)
    segment_type: str
    product: str | None = None
    product_version: str | None = None
    network_element: str | None = None


class Uncertainty(BaseModel):
    field: str
    reason: str
    suggested_options: list[str] = Field(default_factory=list)


class ContextPack(BaseModel):
    query: str
    intent: str
    normalized_query: str
    key_objects: KeyObjects = Field(default_factory=KeyObjects)
    answer_materials: AnswerMaterials = Field(default_factory=AnswerMaterials)
    sources: list[SourceRef] = Field(default_factory=list)
    uncertainties: list[Uncertainty] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    debug_trace: dict | None = None
