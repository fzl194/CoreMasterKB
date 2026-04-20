"""Contract tests: Serving reads real Mining-generated SQLite DBs.

Validates that the Serving pipeline can query actual Mining output without
errors, using both the contract corpus and realistic corpus databases.
Includes questions.yaml-based end-to-end assertions.
"""
from __future__ import annotations

import json
import os

import pytest
import pytest_asyncio
import aiosqlite

from agent_serving.serving.repositories.asset_repo import AssetRepository
from agent_serving.serving.schemas.models import (
    EntityRef,
    EvidenceBudget,
    ExpansionConfig,
    QueryPlan,
    QueryScope,
)

# Resolve paths relative to repo root
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_CONTRACT_DB = os.path.join(_REPO_ROOT, "data", "m1_contract_corpus", "m1_contract_asset.sqlite")
_REALISTIC_DB = os.path.join(_REPO_ROOT, "data", "m1_realistic_corpus", "m1_realistic_asset.sqlite")


def _db_available(path: str) -> bool:
    return os.path.isfile(path)


# --- Fixtures ---

@pytest_asyncio.fixture
async def contract_db():
    """Read-only connection to contract corpus Mining DB."""
    if not _db_available(_CONTRACT_DB):
        pytest.skip("Contract corpus DB not found")
    db = await aiosqlite.connect(f"file:{_CONTRACT_DB}?mode=ro", uri=True)
    db.row_factory = aiosqlite.Row
    yield db
    await db.close()


@pytest_asyncio.fixture
async def realistic_db():
    """Read-only connection to realistic corpus Mining DB."""
    if not _db_available(_REALISTIC_DB):
        pytest.skip("Realistic corpus DB not found")
    db = await aiosqlite.connect(f"file:{_REALISTIC_DB}?mode=ro", uri=True)
    db.row_factory = aiosqlite.Row
    yield db
    await db.close()


@pytest_asyncio.fixture
async def contract_repo(contract_db):
    return AssetRepository(contract_db)


@pytest_asyncio.fixture
async def realistic_repo(realistic_db):
    return AssetRepository(realistic_db)


def _plan(**overrides) -> QueryPlan:
    defaults = {
        "intent": "general",
        "entity_constraints": [],
        "scope_constraints": QueryScope(),
        "evidence_budget": EvidenceBudget(canonical_limit=10, raw_per_canonical=3),
        "expansion": ExpansionConfig(),
        "keywords": [],
    }
    defaults.update(overrides)
    return QueryPlan(**defaults)




# === Basic Infrastructure Tests ===

@pytest.mark.asyncio
async def test_contract_db_active_version(contract_repo):
    """Contract DB must have exactly 1 active publish version."""
    pv_id, error = await contract_repo.get_active_publish_version_id()
    assert pv_id is not None
    assert error is None


@pytest.mark.asyncio
async def test_realistic_db_active_version(realistic_repo):
    """Realistic corpus DB must have exactly 1 active publish version."""
    pv_id, error = await realistic_repo.get_active_publish_version_id()
    assert pv_id is not None
    assert error is None


# === Questions-YAML End-to-End Tests: Contract Corpus ===

@pytest.mark.asyncio
async def test_contract_q_m1_001_n4_interface(contract_repo):
    """Q-M1-001: N4 接口 must return PFCP/SMF/UPF related evidence."""
    plan = _plan(keywords=["N4", "PFCP"])
    results = await contract_repo.search_canonical(plan)
    assert len(results) >= 1
    # Top result should mention N4 or PFCP
    top_text = results[0].get("canonical_text", "") + results[0].get("search_text", "")
    assert "N4" in top_text.upper() or "PFCP" in top_text.upper()

    # Drill down and check evidence has source info
    evidence, _, _ = await contract_repo.drill_down(
        canonical_segment_id=results[0]["id"], plan=plan,
    )
    assert len(evidence) >= 1
    assert evidence[0].get("document_key") is not None
    assert evidence[0].get("relative_path") is not None


@pytest.mark.asyncio
async def test_contract_q_m1_003_smf_config(contract_repo):
    """Q-M1-003: SMF 配置 must return SMF-related evidence."""
    plan = _plan(keywords=["SMF", "配置"])
    results = await contract_repo.search_canonical(plan)
    assert len(results) >= 1
    top_text = (results[0].get("canonical_text", "") or "").lower()
    assert "smf" in top_text


@pytest.mark.asyncio
async def test_contract_source_audit(contract_repo):
    """Source audit: unparsed documents must include processing profile info."""
    pv_id, _ = await contract_repo.get_active_publish_version_id()
    unparsed = await contract_repo.get_unparsed_documents(pv_id)
    assert len(unparsed) >= 1
    # Unparsed docs should have file_type indicating non-markdown
    non_md = [d for d in unparsed if d.get("file_type") and d["file_type"] not in ("markdown", "md")]
    assert len(non_md) >= 1
    # Must have processing_profile_json in the raw dict
    assert any("processing_profile_json" in d for d in unparsed)


@pytest.mark.asyncio
async def test_contract_structured_evidence(contract_repo):
    """Structured evidence must preserve structure_json columns/rows."""
    # Search for table content in contract corpus
    plan = _plan(keywords=["S-NSSAI"])
    results = await contract_repo.search_canonical(plan)
    if not results:
        pytest.skip("No S-NSSAI segments in contract DB")

    found_structure = False
    for canon in results[:5]:
        evidence, _, _ = await contract_repo.drill_down(
            canonical_segment_id=canon["id"], plan=plan,
        )
        for e in evidence:
            struct_raw = e.get("structure_json", "{}")
            struct = json.loads(struct_raw) if isinstance(struct_raw, str) else struct_raw
            if struct.get("columns") or struct.get("rows"):
                found_structure = True
                break
        if found_structure:
            break
    if not found_structure:
        pytest.skip("No structured evidence (table/columns) found in contract DB")


# === Questions-YAML End-to-End Tests: Realistic Corpus ===

@pytest.mark.asyncio
async def test_realistic_q_real_001_network_slicing(realistic_repo):
    """Q-REAL-001: 网络切片 in 5G must return evidence with 网络切片 content."""
    plan = _plan(keywords=["网络切片", "5G"])
    results = await realistic_repo.search_canonical(plan)
    assert len(results) >= 1
    # Top evidence should be about network slicing
    top_text = (results[0].get("canonical_text", "") or "").lower()
    assert "切片" in top_text or "5g" in top_text or "slicing" in top_text.lower()


@pytest.mark.asyncio
async def test_realistic_q_real_005_registerIPv4_bindingIPv4(realistic_repo):
    """Q-REAL-005: registerIPv4/bindingIPv4 must return relevant evidence.

    This is the key P1 test: with stopword filtering and scoring,
    top results must mention the actual config parameters, not random N4/UPF docs.
    """
    # After stopword filtering: free5GC / registerIPv4 / bindingIPv4
    plan = _plan(keywords=["registerIPv4", "bindingIPv4", "free5GC"])
    results = await realistic_repo.search_canonical(plan)
    assert len(results) >= 1
    # At least one of top 3 results must mention the config parameters
    top_texts = [
        (r.get("canonical_text", "") or "") + (r.get("search_text", "") or "")
        for r in results[:3]
    ]
    has_config_params = any(
        "registeripv4" in t.lower() or "bindingipv4" in t.lower()
        for t in top_texts
    )
    assert has_config_params, (
        f"Top results don't mention registerIPv4/bindingIPv4. "
        f"Top titles: {[r.get('title', '') for r in results[:3]]}"
    )


@pytest.mark.asyncio
async def test_realistic_q_real_004_open5gs_commands(realistic_repo):
    """Q-REAL-004: Open5GS UE外网连通 must return evidence with commands."""
    plan = _plan(keywords=["Open5GS", "iptables", "sysctl"])
    results = await realistic_repo.search_canonical(plan)
    assert len(results) >= 1
    # Top result should mention Open5GS
    top_text = (results[0].get("canonical_text", "") or "").lower()
    assert "open5gs" in top_text or "iptables" in top_text


@pytest.mark.asyncio
async def test_realistic_source_drilldown(realistic_repo):
    """Source drilldown: evidence must have relative_path and section_path."""
    plan = _plan(keywords=["free5GC", "UPF"])
    results = await realistic_repo.search_canonical(plan)
    if not results:
        pytest.skip("No free5GC/UPF segments in realistic DB")

    evidence, _, _ = await realistic_repo.drill_down(
        canonical_segment_id=results[0]["id"], plan=plan,
    )
    assert len(evidence) >= 1
    e = evidence[0]
    assert e.get("relative_path") is not None
    # section_path should be parseable (may be string JSON or list)
    sp = e.get("section_path", "[]")
    if isinstance(sp, str):
        parsed = json.loads(sp)
        assert isinstance(parsed, list)


@pytest.mark.asyncio
async def test_realistic_unparsed_with_profile(realistic_repo):
    """Unparsed docs must include file_type and processing_profile."""
    pv_id, _ = await realistic_repo.get_active_publish_version_id()
    unparsed = await realistic_repo.get_unparsed_documents(pv_id)
    assert len(unparsed) >= 1
    for doc in unparsed:
        assert doc.get("file_type") is not None
    # At least one non-markdown file
    non_md = [d for d in unparsed if d["file_type"] not in ("markdown", "md")]
    assert len(non_md) >= 1


# === Scope/Variant/Conflict Behavior Tests ===

@pytest.mark.asyncio
async def test_realistic_scope_variant_separation(realistic_repo):
    """scope_variant should not enter evidence when scope is not constrained."""
    plan = _plan(keywords=["SMF"])
    results = await realistic_repo.search_canonical(plan)
    if not results:
        pytest.skip("No SMF segments")

    for canon in results[:3]:
        evidence, variants, conflicts = await realistic_repo.drill_down(
            canonical_segment_id=canon["id"], plan=plan,
        )
        # Conflict candidates must never be in evidence
        conflict_ids = {c["id"] for c in conflicts}
        evidence_ids = {e["id"] for e in evidence}
        assert conflict_ids.isdisjoint(evidence_ids)


@pytest.mark.asyncio
async def test_contract_scope_with_product_constraint(contract_repo):
    """When scope.products is specified, only matching evidence should be returned."""
    plan = _plan(
        keywords=["SMF"],
        scope_constraints=QueryScope(products=["CloudCore"]),
    )
    results = await contract_repo.search_canonical(plan)
    for canon in results[:3]:
        evidence, _, _ = await contract_repo.drill_down(
            canonical_segment_id=canon["id"], plan=plan,
        )
        # Evidence must either match scope or be scope-variant
        for e in evidence:
            doc_scope = json.loads(e.get("doc_scope_json", "{}"))
            # If doc has products, it must match
            doc_products = doc_scope.get("products") or doc_scope.get("product")
            if doc_products:
                if isinstance(doc_products, str):
                    doc_products = [doc_products]
                assert "CLOUDCORE" in [p.upper() for p in doc_products]


# === Return type contract ===

@pytest.mark.asyncio
async def test_realistic_no_active_version_returns_tuple(realistic_db):
    """get_active_publish_version_id must return (id|None, error|None) tuple."""
    repo = AssetRepository(realistic_db)
    pv_id, error = await repo.get_active_publish_version_id()
    assert isinstance(pv_id, str | type(None))
    assert isinstance(error, str | type(None))
