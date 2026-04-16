"""Tests for schema adapter -- PostgreSQL to SQLite DDL conversion."""
import os
import pytest
import aiosqlite
from agent_serving.serving.repositories.schema_adapter import (
    build_sqlite_ddl_from_asset_schema,
    create_asset_tables_sqlite,
)


SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "knowledge_assets", "schemas", "001_asset_core.sql",
)


def test_build_sqlite_ddl_produces_all_tables():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        pg_sql = f.read()
    ddl = build_sqlite_ddl_from_asset_schema(pg_sql)
    assert "asset_publish_versions" in ddl
    assert "asset_raw_documents" in ddl
    assert "asset_raw_segments" in ddl
    assert "asset_canonical_segments" in ddl
    assert "asset_canonical_segment_sources" in ddl


def test_no_pg_specific_syntax():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        pg_sql = f.read()
    ddl = build_sqlite_ddl_from_asset_schema(pg_sql)
    assert "CREATE EXTENSION" not in ddl
    assert "CREATE SCHEMA" not in ddl
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
    assert "asset_publish_versions" in tables
    assert "asset_raw_documents" in tables
    assert "asset_raw_segments" in tables
    assert "asset_canonical_segments" in tables
    assert "asset_canonical_segment_sources" in tables
    await db.close()
