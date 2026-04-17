"""Search API — unified QueryPlan pipeline for generic evidence retrieval.

/search is the main entry. /command-usage is a compatible shortcut.
Explicit request scope/entities take priority over normalizer extraction.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from agent_serving.serving.schemas.models import (
    CommandUsageRequest,
    EntityRef,
    EvidencePack,
    NormalizedQuery,
    QueryPlan,
    QueryScope,
    SearchRequest,
)
from agent_serving.serving.repositories.asset_repo import AssetRepository
from agent_serving.serving.application.normalizer import QueryNormalizer, build_plan
from agent_serving.serving.application.assembler import EvidenceAssembler

router = APIRouter(prefix="/api/v1", tags=["search"])


def get_repo(request: Request) -> AssetRepository:
    return AssetRepository(request.app.state.db)


def _merge_explicit_overrides(
    normalized: NormalizedQuery, req_scope: QueryScope | None, req_entities: list[EntityRef] | None,
) -> NormalizedQuery:
    """Merge explicit request scope/entities over normalizer extraction.

    Returns a new NormalizedQuery instance — never mutates the input.
    """
    updates: dict = {}
    if req_scope:
        updates["scope"] = req_scope
        updates["missing_constraints"] = []
    if req_entities:
        updates["entities"] = req_entities

    if not updates:
        return normalized
    return normalized.model_copy(update=updates)


async def _execute_plan(
    query: str, normalized: NormalizedQuery, plan: QueryPlan, repo: AssetRepository,
) -> EvidencePack:
    """Core pipeline: search canonical → drill down → assemble evidence pack."""
    assembler = EvidenceAssembler()

    # Validate active version
    pv_id, pv_error = await repo.get_active_publish_version_id()
    if pv_error == "no_active_version":
        raise HTTPException(status_code=503, detail="No active asset version — knowledge base is empty")
    if pv_error == "multiple_active_versions":
        raise HTTPException(status_code=500, detail="Data integrity error: multiple active versions")

    # 1. Search L1 canonical segments
    canonical_hits = await repo.search_canonical(plan, pv_id)

    # 2. Fallback: if entity search found nothing, try keywords
    if not canonical_hits and plan.keywords:
        keyword_plan = QueryPlan(
            intent=plan.intent,
            retrieval_targets=plan.retrieval_targets,
            entity_constraints=[],
            scope_constraints=plan.scope_constraints,
            semantic_role_preferences=plan.semantic_role_preferences,
            block_type_preferences=plan.block_type_preferences,
            variant_policy=plan.variant_policy,
            conflict_policy=plan.conflict_policy,
            evidence_budget=plan.evidence_budget,
            expansion=plan.expansion,
            keywords=plan.keywords,
        )
        canonical_hits = await repo.search_canonical(keyword_plan, pv_id)

    # 3. Drill down for each canonical hit (concurrent)
    drill_results = await asyncio.gather(*[
        repo.drill_down(
            canonical_segment_id=canon["id"],
            plan=plan,
            pv_id=pv_id,
        )
        for canon in canonical_hits
    ])

    # 4. Get unparsed documents for source audit
    unparsed = await repo.get_unparsed_documents(pv_id)

    # 5. Assemble evidence pack
    pack = assembler.assemble(
        query=query,
        intent=plan.intent,
        normalized=normalized,
        plan=plan,
        canonical_hits=canonical_hits,
        drill_results=drill_results,
        unparsed_docs=unparsed,
    )

    return pack


@router.post("/search", response_model=EvidencePack)
async def search(
    request: SearchRequest,
    repo: AssetRepository = Depends(get_repo),
) -> EvidencePack:
    normalizer = QueryNormalizer()
    normalized = normalizer.normalize(request.query)

    # Merge explicit overrides
    normalized = _merge_explicit_overrides(normalized, request.scope, request.entities)
    plan = build_plan(normalized)

    return await _execute_plan(request.query, normalized, plan, repo)


@router.post("/command-usage", response_model=EvidencePack)
async def command_usage(
    request: CommandUsageRequest,
    repo: AssetRepository = Depends(get_repo),
) -> EvidencePack:
    """Compatible shortcut: forces intent=command_usage."""
    normalizer = QueryNormalizer()
    normalized = normalizer.normalize(request.query)

    has_command = any(e.type == "command" for e in normalized.entities)
    if not has_command:
        raise HTTPException(status_code=400, detail="Could not identify a command in the query")

    normalized = normalized.model_copy(update={
        "intent": "command_usage",
        "desired_semantic_roles": ["parameter", "example", "procedure_step"],
    })

    plan = build_plan(normalized)
    return await _execute_plan(request.query, normalized, plan, repo)
