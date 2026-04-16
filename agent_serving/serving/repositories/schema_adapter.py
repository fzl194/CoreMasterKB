"""Schema adapter: convert PostgreSQL asset DDL to SQLite-compatible DDL.

This module reads the shared schema contract at
`knowledge_assets/schemas/001_asset_core.sql` and produces
SQLite-compatible DDL. It is the ONLY place where asset table
structure is defined for dev/test mode.

No other code in agent_serving should maintain private asset DDL.
"""
from __future__ import annotations

import os
import re

import aiosqlite

_SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "knowledge_assets", "schemas", "001_asset_core.sql",
)


def load_asset_schema_sql() -> str:
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return f.read()


def build_sqlite_ddl_from_asset_schema(pg_sql: str) -> str:
    """Convert PostgreSQL asset DDL to SQLite-compatible DDL."""
    lines = pg_sql.split("\n")
    output_lines: list[str] = []
    skip_block = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("CREATE EXTENSION") or stripped.startswith("CREATE SCHEMA"):
            continue

        if stripped.startswith("CREATE ") and "INDEX" in stripped.upper():
            skip_block = True
            continue

        if skip_block and not stripped.endswith(";"):
            continue
        if skip_block and stripped.endswith(";"):
            skip_block = False
            continue

        line = re.sub(r'\basset\.', "asset_", line)
        line = line.replace("UUID", "TEXT")
        line = line.replace("JSONB", "TEXT")
        line = line.replace("TIMESTAMPTZ", "TEXT")
        line = line.replace("NUMERIC(5,4)", "REAL")
        line = re.sub(r"DEFAULT gen_random_uuid\(\)", "", line)
        line = line.replace("'[]'::jsonb", "'[]'")
        line = line.replace("'{}'::jsonb", "'{}'")
        line = line.replace("DEFAULT NOW()", "DEFAULT (datetime('now'))")

        if "jsonb_typeof" in line:
            continue

        output_lines.append(line)

    return "\n".join(output_lines)


async def create_asset_tables_sqlite(db: aiosqlite.Connection) -> None:
    """Create all asset tables in a SQLite database using shared schema."""
    pg_sql = load_asset_schema_sql()
    sqlite_ddl = build_sqlite_ddl_from_asset_schema(pg_sql)
    await db.executescript(sqlite_ddl)
    await db.commit()
