"""Tests for schema adapter — v1.1 SQLite DDL loading."""
import pytest
import aiosqlite
from agent_serving.serving.repositories.schema_adapter import (
    load_sqlite_ddl,
    create_asset_tables_sqlite,
)


def test_load_sqlite_ddl_contains_all_tables():
    ddl = load_sqlite_ddl()
    # v1.1 tables
    assert "asset_source_batches" in ddl
    assert "asset_documents" in ddl
    assert "asset_document_snapshots" in ddl
    assert "asset_document_snapshot_links" in ddl
    assert "asset_raw_segments" in ddl
    assert "asset_raw_segment_relations" in ddl
    assert "asset_retrieval_units" in ddl
    assert "asset_builds" in ddl
    assert "asset_build_document_snapshots" in ddl
    assert "asset_publish_releases" in ddl


def test_sqlite_ddl_has_no_pg_syntax():
    ddl = load_sqlite_ddl()
    assert "JSONB" not in ddl
    assert "TIMESTAMPTZ" not in ddl
    assert "gen_random_uuid" not in ddl


@pytest.mark.asyncio
async def test_create_tables_in_sqlite():
    db = await aiosqlite.connect(":memory:")
    await create_asset_tables_sqlite(db)
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in await cursor.fetchall()]
    assert "asset_source_batches" in tables
    assert "asset_documents" in tables
    assert "asset_document_snapshots" in tables
    assert "asset_raw_segments" in tables
    assert "asset_retrieval_units" in tables
    assert "asset_builds" in tables
    assert "asset_publish_releases" in tables
    await db.close()


@pytest.mark.asyncio
async def test_sqlite_ddl_has_v11_fields():
    """Verify v1.1 fields exist in the created tables."""
    db = await aiosqlite.connect(":memory:")
    await create_asset_tables_sqlite(db)

    # raw_segments should have entity_refs_json, block_type, semantic_role
    cursor = await db.execute("PRAGMA table_info(asset_raw_segments)")
    cols = {row[1] for row in await cursor.fetchall()}
    assert "entity_refs_json" in cols
    assert "block_type" in cols
    assert "semantic_role" in cols
    assert "document_snapshot_id" in cols

    # retrieval_units should have source_refs_json, facets_json
    cursor = await db.execute("PRAGMA table_info(asset_retrieval_units)")
    cols = {row[1] for row in await cursor.fetchall()}
    assert "source_refs_json" in cols
    assert "facets_json" in cols
    assert "text" in cols
    assert "search_text" in cols

    # publish_releases should have channel, status
    cursor = await db.execute("PRAGMA table_info(asset_publish_releases)")
    cols = {row[1] for row in await cursor.fetchall()}
    assert "channel" in cols
    assert "build_id" in cols
    assert "status" in cols

    await db.close()
