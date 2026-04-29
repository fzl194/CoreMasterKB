"""Tests for DenseVectorRetriever — pgvector backend."""
import pytest
import pytest_asyncio

from agent_serving.serving.schemas.models import RetrievalQuery
from agent_serving.serving.retrieval.dense_vector_retriever import DenseVectorRetriever


@pytest_asyncio.fixture
async def retriever(pg_pool):
    return DenseVectorRetriever(pg_pool, embedding_dimensions=1024)


@pytest.mark.pg
class TestDenseVectorRetriever:
    @pytest.mark.asyncio
    async def test_retrieve_returns_empty_when_no_query_embedding(self, retriever):
        rq = RetrievalQuery(original_query="test")
        results = await retriever.retrieve(rq, ["snap1"])
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_empty_snapshot(self, retriever):
        rq = RetrievalQuery(original_query="test", query_embedding=[1.0] * 1024)
        results = await retriever.retrieve(rq, [])
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_empty_query_embedding(self, retriever):
        rq = RetrievalQuery(original_query="test", query_embedding=[])
        results = await retriever.retrieve(rq, ["snap1"])
        assert len(results) == 0
