"""Search API — query L1 canonical_segments, drill down to L0 via L2."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from agent_serving.serving.schemas.models import (
    CommandUsageRequest,
    ContextPack,
    SearchRequest,
)
from agent_serving.serving.repositories.asset_repo import AssetRepository
from agent_serving.serving.application.normalizer import QueryNormalizer
from agent_serving.serving.application.assembler import ContextAssembler

router = APIRouter(prefix="/api/v1", tags=["search"])


def get_repo(request: Request) -> AssetRepository:
    return AssetRepository(request.app.state.db)


def _intent_from_query(normalized) -> str:
    if normalized.command:
        return "command_usage"
    return "general_query"


@router.post("/search", response_model=ContextPack)
async def search(
    request: SearchRequest,
    repo: AssetRepository = Depends(get_repo),
) -> ContextPack:
    normalizer = QueryNormalizer()
    assembler = ContextAssembler()

    normalized = normalizer.normalize(request.query)

    # Search L1 canonical segments
    canonical_hits = await repo.search_canonical(
        command_name=normalized.command,
        keyword=normalized.keywords[0] if normalized.keywords and not normalized.command else None,
    )

    # If keyword search found nothing and keywords exist, try each keyword
    if not canonical_hits and normalized.keywords and not normalized.command:
        for kw in normalized.keywords:
            canonical_hits = await repo.search_canonical(keyword=kw)
            if canonical_hits:
                break

    # If command search found nothing, try keyword with command name
    if not canonical_hits and normalized.command:
        canonical_hits = await repo.search_canonical(
            keyword=normalized.command.split()[-1] if normalized.command else None,
        )

    intent = _intent_from_query(normalized)

    # Fetch drill-down and conflict data for each canonical hit
    all_drill: list[dict] = []
    all_conflicts: list[dict] = []
    for canon in canonical_hits:
        drill = await repo.drill_down(
            canonical_segment_id=canon["id"],
            product=normalized.product,
            product_version=normalized.product_version,
            network_element=normalized.network_element,
            exclude_conflict=True,
        )
        all_drill.extend(drill)
        conflicts = await repo.get_conflict_sources(
            canonical_segment_id=canon["id"],
        )
        all_conflicts.extend(conflicts)

    pack = assembler.assemble(
        query=request.query,
        intent=intent,
        normalized=normalized,
        canonical_hits=canonical_hits,
        drill_results=all_drill,
        conflict_sources=all_conflicts,
    )

    return pack


@router.post("/command-usage", response_model=ContextPack)
async def command_usage(
    request: CommandUsageRequest,
    repo: AssetRepository = Depends(get_repo),
) -> ContextPack:
    """Dedicated command usage endpoint — requires command context."""
    normalizer = QueryNormalizer()
    assembler = ContextAssembler()

    normalized = normalizer.normalize(request.query)
    if not normalized.command:
        raise HTTPException(
            status_code=400,
            detail="Could not identify a command in the query",
        )

    canonical_hits = await repo.search_canonical(command_name=normalized.command)
    if not canonical_hits:
        canonical_hits = await repo.search_canonical(
            keyword=normalized.command.split()[-1],
        )

    all_drill: list[dict] = []
    all_conflicts: list[dict] = []
    for canon in canonical_hits:
        drill = await repo.drill_down(
            canonical_segment_id=canon["id"],
            product=normalized.product,
            product_version=normalized.product_version,
            network_element=normalized.network_element,
            exclude_conflict=True,
        )
        all_drill.extend(drill)
        conflicts = await repo.get_conflict_sources(
            canonical_segment_id=canon["id"],
        )
        all_conflicts.extend(conflicts)

    pack = assembler.assemble(
        query=request.query,
        intent="command_usage",
        normalized=normalized,
        canonical_hits=canonical_hits,
        drill_results=all_drill,
        conflict_sources=all_conflicts,
    )

    return pack
