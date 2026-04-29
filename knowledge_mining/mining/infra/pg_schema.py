"""PostgreSQL schema initialization for Mining v3.0."""
from __future__ import annotations

import logging
from pathlib import Path

import psycopg

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ASSET_DDL = _REPO_ROOT / "databases" / "asset_core" / "schemas" / "002_asset_core_postgresql.sql"
_RUNTIME_DDL = _REPO_ROOT / "databases" / "mining_runtime" / "schemas" / "002_mining_runtime_postgresql.sql"


def ensure_schema(conn: psycopg.Connection) -> None:
    """Execute both PostgreSQL DDL files to ensure tables exist."""
    for ddl_path in (_ASSET_DDL, _RUNTIME_DDL):
        ddl = ddl_path.read_text(encoding="utf-8")
        # Execute each statement separately (psycopg doesn't have executescript)
        with conn.cursor() as cur:
            cur.execute(ddl)
        logger.info("Applied DDL: %s", ddl_path.name)
    conn.commit()
