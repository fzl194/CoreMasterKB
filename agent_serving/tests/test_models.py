"""Tests for v1.1 data models."""
import pytest

from agent_serving.serving.schemas.models import (
    ActiveScope,
    ContextItem,
    ContextPack,
    ContextQuery,
    ContextRelation,
    EntityRef,
    ExpansionConfig,
    Issue,
    NormalizedQuery,
    QueryPlan,
    RetrievalBudget,
    RetrievalCandidate,
    SearchRequest,
    SourceRef,
)
from agent_serving.serving.schemas.constants import (
    INTENT_COMMAND_USAGE,
    KIND_RAW_SEGMENT,
    KIND_RETRIEVAL_UNIT,
    ROLE_SEED,
    ROLE_CONTEXT,
)


class TestSearchRequest:
    def test_minimal(self):
        req = SearchRequest(query="ADD APN")
        assert req.query == "ADD APN"
        assert req.scope is None
        assert req.entities is None
        assert req.debug is False

    def test_full(self):
        req = SearchRequest(
            query="ADD APN",
            scope={"products": ["UDG"]},
            entities=[EntityRef(type="command", name="ADD APN")],
            debug=True,
        )
        assert req.scope == {"products": ["UDG"]}
        assert len(req.entities) == 1
        assert req.debug is True


class TestNormalizedQuery:
    def test_defaults(self):
        nq = NormalizedQuery()
        assert nq.intent == "general"
        assert nq.entities == []
        assert nq.scope == {}
        assert nq.keywords == []

    def test_with_values(self):
        nq = NormalizedQuery(
            original_query="ADD APN怎么用",
            intent=INTENT_COMMAND_USAGE,
            entities=[EntityRef(type="command", name="ADD APN")],
            scope={"products": ["UDG"]},
            keywords=["APN", "配置"],
            desired_roles=["parameter", "example"],
        )
        assert nq.intent == INTENT_COMMAND_USAGE
        assert len(nq.entities) == 1
        assert nq.desired_roles == ["parameter", "example"]


class TestQueryPlan:
    def test_defaults(self):
        plan = QueryPlan()
        assert plan.budget.max_items == 10
        assert plan.expansion.enable_relation_expansion is True
        assert plan.expansion.max_relation_depth == 2

    def test_budget_override(self):
        plan = QueryPlan(budget=RetrievalBudget(max_items=5))
        assert plan.budget.max_items == 5


class TestActiveScope:
    def test_construction(self):
        scope = ActiveScope(
            release_id="rel-1",
            build_id="build-1",
            snapshot_ids=["snap-1", "snap-2"],
            document_snapshot_map={"doc-1": "snap-1"},
        )
        assert len(scope.snapshot_ids) == 2
        assert scope.document_snapshot_map["doc-1"] == "snap-1"


class TestContextPack:
    def test_empty_pack(self):
        pack = ContextPack(
            query=ContextQuery(original="test", normalized="test", intent="general"),
        )
        assert pack.items == []
        assert pack.relations == []
        assert pack.sources == []
        assert pack.issues == []
        assert pack.suggestions == []

    def test_full_pack(self):
        pack = ContextPack(
            query=ContextQuery(original="ADD APN", normalized="intent=command_usage", intent="command_usage"),
            items=[
                ContextItem(id="ru-1", kind=KIND_RETRIEVAL_UNIT, role=ROLE_SEED, text="text", score=1.0),
                ContextItem(id="seg-1", kind=KIND_RAW_SEGMENT, role=ROLE_CONTEXT, text="raw", score=0.0),
            ],
            relations=[
                ContextRelation(id="rel-1", from_id="seg-1", to_id="seg-2", relation_type="next", distance=1),
            ],
            sources=[
                SourceRef(id="doc-1", document_key="UDG_OM"),
            ],
            issues=[
                Issue(type="no_result", message="empty"),
            ],
            suggestions=["try different keywords"],
        )
        assert len(pack.items) == 2
        assert len(pack.relations) == 1
        assert pack.items[0].role == ROLE_SEED
        assert pack.relations[0].relation_type == "next"

    def test_serialization(self):
        pack = ContextPack(
            query=ContextQuery(original="test", normalized="test", intent="general"),
        )
        data = pack.model_dump()
        assert isinstance(data, dict)
        assert "items" in data
        assert "relations" in data

        # Round-trip
        restored = ContextPack.model_validate(data)
        assert restored.query.original == "test"


class TestRetrievalCandidate:
    def test_construction(self):
        c = RetrievalCandidate(
            retrieval_unit_id="ru-1",
            score=0.95,
            source="fts_bm25",
        )
        assert c.score == 0.95
        assert c.source == "fts_bm25"
        assert c.metadata == {}
