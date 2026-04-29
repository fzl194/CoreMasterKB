"""PostgreSQL schema initialization for Mining v3.0.

Ensures the target database exists (creates if needed),
then applies DDL for both asset_core and mining_runtime tables.
"""
from __future__ import annotations

import logging
from pathlib import Path

import psycopg

from .pg_config import MiningDbConfig

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ASSET_DDL = _REPO_ROOT / "databases" / "asset_core" / "schemas" / "002_asset_core_postgresql.sql"
_RUNTIME_DDL = _REPO_ROOT / "databases" / "mining_runtime" / "schemas" / "002_mining_runtime_postgresql.sql"


def ensure_database(cfg: MiningDbConfig) -> None:
    """Create the target database if it doesn't exist (connects to postgres maintenance DB)."""
    conn = psycopg.connect(cfg.maintenance_conninfo, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (cfg.pg_dbname,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE {cfg.pg_dbname}')
                logger.info("Created database %s", cfg.pg_dbname)
            else:
                logger.info("Database %s already exists", cfg.pg_dbname)
    finally:
        conn.close()


def ensure_schema(cfg: MiningDbConfig) -> None:
    """Ensure database exists, then execute both DDL files."""
    ensure_database(cfg)

    conn = psycopg.connect(cfg.conninfo, autocommit=True)
    try:
        for ddl_path in (_ASSET_DDL, _RUNTIME_DDL):
            ddl = ddl_path.read_text(encoding="utf-8")
            with conn.cursor() as cur:
                cur.execute(ddl)
            logger.info("Applied DDL: %s", ddl_path.name)
    finally:
        conn.close()
