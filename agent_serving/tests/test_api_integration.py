"""Integration tests: full search pipeline via FastAPI TestClient."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from agent_serving.serving.main import app
from agent_serving.serving.repositories.schema_adapter import create_asset_tables_sqlite
from agent_serving.tests.conftest import _seed_data


@pytest_asyncio.fixture
async def client():
    """Test client with in-memory DB seeded from shared schema."""
    db = await _create_seeded_db()
    app.state.db = db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await db.close()


async def _create_seeded_db():
    import aiosqlite
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await create_asset_tables_sqlite(db)
    await _seed_data(db)
    return db


@pytest.mark.asyncio
async def test_health_check(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_search_command_query(client):
    resp = await client.post("/api/v1/search", json={"query": "ADD APN 怎么写"})
    assert resp.status_code == 200
    pack = resp.json()
    assert pack["intent"] == "command_usage"
    assert len(pack["answer_materials"]["canonical_segments"]) >= 1
    assert pack["answer_materials"]["canonical_segments"][0]["command_name"] == "ADD APN"


@pytest.mark.asyncio
async def test_search_keyword_query(client):
    resp = await client.post("/api/v1/search", json={"query": "5G 移动通信"})
    assert resp.status_code == 200
    pack = resp.json()
    assert pack["intent"] == "general_query"
    assert len(pack["answer_materials"]["canonical_segments"]) >= 1
    assert "5G" in pack["answer_materials"]["canonical_segments"][0]["canonical_text"]


@pytest.mark.asyncio
async def test_search_with_product_filter(client):
    resp = await client.post("/api/v1/search", json={"query": "UDG V100R023C10 ADD APN"})
    assert resp.status_code == 200
    pack = resp.json()
    assert len(pack["answer_materials"]["raw_segments"]) >= 1
    # All raw segments should be from UDG
    for src in pack["sources"]:
        if src.get("product"):
            assert src["product"] == "UDG"


@pytest.mark.asyncio
async def test_command_usage_endpoint(client):
    resp = await client.post("/api/v1/command-usage", json={"query": "ADD APN"})
    assert resp.status_code == 200
    pack = resp.json()
    assert pack["intent"] == "command_usage"


@pytest.mark.asyncio
async def test_command_usage_no_command(client):
    resp = await client.post("/api/v1/command-usage", json={"query": "5G是什么"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_conflict_does_not_appear_in_raw_segments(client):
    """Conflict candidates must become uncertainties, not raw_segments."""
    resp = await client.post("/api/v1/search", json={"query": "ADD APN"})
    assert resp.status_code == 200
    pack = resp.json()
    # Conflict text should NOT appear in raw_segments
    raw_texts = [r["raw_text"] for r in pack["answer_materials"]["raw_segments"]]
    for rt in raw_texts:
        assert "参数冲突版本" not in rt
    # But should appear in uncertainties
    if pack["uncertainties"]:
        assert any("冲突" in u["reason"] for u in pack["uncertainties"])
