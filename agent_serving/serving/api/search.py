"""Search API — v1.1 /search endpoint.

Single endpoint: /api/v1/search
Pipeline: normalize → plan → resolve scope → retrieve → expand → assemble
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from agent_serving.serving.schemas.models import (
    ActiveScope,
    ContextPack,
    QueryPlan,
    RetrievalBudget,
    ExpansionConfig,
    SearchRequest,
)
from agent_serving.serving.repositories.asset_repo import AssetRepository
from agent_serving.serving.retrieval.bm25_retriever import FTS5BM25Retriever
from agent_serving.serving.retrieval.graph_expander import GraphExpander
from agent_serving.serving.application.normalizer import QueryNormalizer
from agent_serving.serving.application.assembler import ContextAssembler

router = APIRouter(prefix="/api/v1", tags=["search"])


def _get_repo(request: Request) -> AssetRepository:
    return AssetRepository(request.app.state.db)


def _get_retriever(request: Request) -> FTS5BM25Retriever:
    return FTS5BM25Retriever(request.app.state.db)


def _get_expander(request: Request) -> GraphExpander:
    return GraphExpander(request.app.state.db)


def _build_plan(request: SearchRequest, normalized) -> QueryPlan:
    """Build QueryPlan from request + normalized query."""
    scope = normalized.scope
    if request.scope:
        scope = request.scope

    entities = normalized.entities
    if request.entities:
        entities = request.entities

    return QueryPlan(
        intent=normalized.intent,
        keywords=normalized.keywords,
        entity_constraints=entities,
        scope_constraints=scope,
        desired_roles=normalized.desired_roles,
        desired_block_types=[],
        budget=RetrievalBudget(),
        expansion=ExpansionConfig(),
    )


@router.post("/search", response_model=ContextPack)
async def search(
    request: SearchRequest,
    repo: AssetRepository = Depends(_get_repo),
    retriever: FTS5BM25Retriever = Depends(_get_retriever),
    expander: GraphExpander = Depends(_get_expander),
) -> ContextPack:
    normalizer = QueryNormalizer()
    normalized = normalizer.normalize(request.query)

    # Merge explicit overrides
    if request.scope:
        normalized = normalized.model_copy(update={"scope": request.scope})
    if request.entities:
        normalized = normalized.model_copy(update={"entities": request.entities})

    plan = _build_plan(request, normalized)

    # Resolve active scope (release → build → snapshots)
    try:
        scope = await repo.resolve_active_scope()
    except ValueError as e:
        if str(e) == "no_active_release":
            raise HTTPException(
                status_code=503,
                detail="No active release — knowledge base is empty",
            )
        if str(e) == "multiple_active_releases":
            raise HTTPException(
                status_code=500,
                detail="Data integrity error: multiple active releases",
            )
        raise

    # Retrieve candidates via FTS5
    candidates = await retriever.retrieve(plan, scope.snapshot_ids)

    # Assemble ContextPack
    assembler = ContextAssembler(repo, expander)
    pack = await assembler.assemble(
        query=request.query,
        normalized=normalized,
        plan=plan,
        scope=scope,
        candidates=candidates,
    )

    if request.debug:
        pack = pack.model_copy(update={
            "debug": {
                "plan": plan.model_dump(),
                "scope": scope.model_dump(),
                "candidate_count": len(candidates),
            },
        })

    return pack
