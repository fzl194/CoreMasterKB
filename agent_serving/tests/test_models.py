"""Verify Pydantic models serialize/deserialize correctly."""
import pytest
from agent_serving.serving.schemas.models import (
    SearchRequest,
    CommandUsageRequest,
    ContextPack,
    NormalizedQuery,
    KeyObjects,
    AnswerMaterials,
)


def test_search_request_defaults():
    req = SearchRequest(query="ADD APN 怎么写")
    assert req.query == "ADD APN 怎么写"


def test_command_usage_request():
    req = CommandUsageRequest(query="UDG V100R023C10 ADD APN")
    assert req.query == "UDG V100R023C10 ADD APN"


def test_normalized_query_missing_constraints():
    nq = NormalizedQuery(
        command="ADD APN",
        product=None,
        product_version=None,
        network_element=None,
        keywords=[],
        missing_constraints=["product", "product_version"],
    )
    assert "product" in nq.missing_constraints


def test_context_pack_serialization():
    pack = ContextPack(
        query="ADD APN",
        intent="command_usage",
        normalized_query="ADD APN",
        key_objects=KeyObjects(command="ADD APN"),
        answer_materials=AnswerMaterials(canonical_segments=[], raw_segments=[]),
        sources=[],
        uncertainties=[],
        suggested_followups=[],
    )
    data = pack.model_dump()
    assert data["intent"] == "command_usage"
    assert data["answer_materials"]["canonical_segments"] == []
