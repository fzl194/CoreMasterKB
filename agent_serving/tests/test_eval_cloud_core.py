"""Eval: 30 eval questions against /api/v1/search with Recall@K/MRR@K/NDCG@K.

Uses the real DB (data/kb-asset_core.sqlite) and the real API endpoint.
External services are disabled to measure BM25+entity baseline.
Leverages the existing EvalRunner for metric computation.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
import aiosqlite
import yaml
from httpx import ASGITransport, AsyncClient

from agent_serving.serving.main import app
from agent_serving.serving.eval.runner import EvalRunner

REAL_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "kb-asset_core.sqlite"
DOMAIN_YAML_PATH = (
    Path(__file__).resolve().parents[2]
    / "knowledge_mining" / "domain_packs" / "cloud_core_network" / "domain.yaml"
)

pytestmark = pytest.mark.skipif(
    not REAL_DB_PATH.exists(),
    reason="Real DB not found — skipping eval",
)


def _load_eval_questions() -> list[dict]:
    """Load eval questions from domain.yaml."""
    with open(DOMAIN_YAML_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("eval_questions", [])


@pytest_asyncio.fixture
async def eval_client():
    """Test client wired to real DB, external services disabled."""
    lifespan_db = getattr(app.state, "db", None)
    if lifespan_db:
        await lifespan_db.close()

    db = await aiosqlite.connect(str(REAL_DB_PATH))
    db.row_factory = aiosqlite.Row
    app.state.db = db
    app.state.llm_client = None
    app.state.embedding_generator = None
    app.state.domain_profile = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await db.close()


class TestEvalCloudCore:
    """Run 30 eval questions and compute Recall@K/MRR@K/NDCG@K."""

    @pytest.mark.asyncio
    async def test_eval_30_questions(self, eval_client):
        """Run all eval questions via API and output metrics."""
        questions = _load_eval_questions()
        assert len(questions) >= 25, (
            f"Expected >= 25 eval questions, got {len(questions)}"
        )

        K = 10

        # Build search_fn that calls the real API
        async def search_fn(query: str) -> dict:
            resp = await eval_client.post(
                "/api/v1/search", json={"query": query},
            )
            assert resp.status_code == 200, (
                f"Query '{query}' returned {resp.status_code}"
            )
            return resp.json()

        # Use EvalRunner for metric computation
        runner = EvalRunner(k=K)
        report = await runner.run(questions, search_fn)

        # Print structured results
        print("\n" + "=" * 60)
        print(f"EVAL RESULTS: Cloud Core Network ({report.total_questions} questions)")
        print("=" * 60)
        print(f"  HitRate@{K}:   {report.hit_rate:.4f}")
        print(f"  Recall@{K}:    {report.recall_at_k:.4f}")
        print(f"  MRR@{K}:       {report.mrr_at_k:.4f}")
        print(f"  NDCG@{K}:      {report.ndcg_at_k:.4f}")
        print(f"  Total queries: {report.total_questions}")
        print(f"  Hits:          {sum(1 for r in report.results if r.hit)}")
        if report.route_contribution:
            print(f"  Route contribution:")
            for route, count in sorted(report.route_contribution.items()):
                print(f"    {route}: {count}")
        print("=" * 60)

        # Per-question results for failures
        failures = [r for r in report.results if not r.hit]
        if failures:
            print(f"\n  Missed questions ({len(failures)}):")
            for r in failures:
                print(f"    {r.question_id}: {r.question}")

        # Baseline assertion: HitRate@10 >= 0.3 (BM25+entity baseline without LLM/embedding)
        # Measured initial baseline: 0.37 (11/30 hits, rule-only path)
        # This threshold protects against regression; room for improvement with LLM/rerank
        assert report.hit_rate >= 0.3, (
            f"HitRate@{K} = {report.hit_rate:.4f} < 0.3 baseline. "
            f"Check main chain integrity."
        )

        # All queries must return items (even if not relevant)
        for r in report.results:
            assert r.top_item_score >= 0, (
                f"Question {r.question_id} returned no items"
            )
