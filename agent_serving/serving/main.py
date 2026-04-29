"""FastAPI application with PostgreSQL backend.

Reads PG connection from .env (PG_HOST, PG_PORT, etc.).
Uses psycopg async pool for all database operations.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from agent_serving.serving.api.health import router as health_router
from agent_serving.serving.api.search import router as search_router
from agent_serving.serving.repositories.asset_repo import AssetRepository

logger = logging.getLogger(__name__)

_PG_ENV_VARS = ("PG_HOST", "PG_PORT", "PG_DBNAME", "PG_USER", "PG_PASSWORD")


def _build_conninfo() -> str:
    """Build psycopg conninfo from environment variables."""
    host = os.environ.get("PG_HOST", "localhost")
    port = os.environ.get("PG_PORT", "5432")
    dbname = os.environ.get("PG_DBNAME", "coremasterkb")
    user = os.environ.get("PG_USER", "kb_user")
    password = os.environ.get("PG_PASSWORD", "")
    sslmode = os.environ.get("PG_SSLMODE", "disable")
    gssencmode = os.environ.get("PG_GSSENCMODE", "disable")
    return (
        f"host={host} port={port} dbname={dbname} user={user} "
        f"password={password} sslmode={sslmode} gssencmode={gssencmode}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    conninfo = _build_conninfo()

    pool = AsyncConnectionPool(
        conninfo,
        min_size=2,
        max_size=10,
        open=False,
        kwargs={"row_factory": dict_row},
    )
    await pool.open()
    app.state.pg_pool = pool

    # Cache domain profile if configured
    domain_id = os.environ.get("COREMASTERKB_DOMAIN")
    if domain_id:
        try:
            from agent_serving.serving.domain_pack_reader import load_serving_profile
            app.state.domain_profile = load_serving_profile(domain_id)
        except Exception:
            pass
    else:
        app.state.domain_profile = None

    # Initialize LLM client (lazy — no health check at startup)
    app.state.llm_client = None
    try:
        from agent_serving.serving.infrastructure.llm_client import ServingLlmClient
        llm_base_url = os.environ.get("LLM_SERVICE_URL", "http://localhost:8900")
        app.state.llm_client = ServingLlmClient(base_url=llm_base_url)
        logger.info("LLM client configured for %s (availability checked at first use)", llm_base_url)
    except Exception:
        logger.warning("Failed to initialize LLM client, using rule fallback", exc_info=True)

    # Initialize embedding generator
    app.state.embedding_generator = None
    embedding_api_key = os.environ.get("EMBEDDING_API_KEY")
    if embedding_api_key:
        try:
            from agent_serving.serving.infrastructure.embedding import EmbeddingGenerator
            app.state.embedding_generator = EmbeddingGenerator(
                api_key=embedding_api_key,
                model=os.environ.get("EMBEDDING_MODEL", "embedding-3"),
                base_url=os.environ.get("EMBEDDING_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
                dimensions=int(os.environ.get("EMBEDDING_DIMENSIONS", "1024")),
            )
            logger.info("Embedding generator initialized (model=%s)", os.environ.get("EMBEDDING_MODEL", "embedding-3"))
        except Exception:
            logger.warning("Failed to initialize embedding generator", exc_info=True)

    yield

    # Cleanup
    if app.state.llm_client:
        await app.state.llm_client.close()
    await pool.close()


async def get_repo(request: Request) -> AssetRepository:
    async with request.app.state.pg_pool.connection() as conn:
        return AssetRepository(conn)


app = FastAPI(
    title="Cloud Core Knowledge Backend",
    version="0.3.0",
    description="Agent Knowledge Backend for cloud core network — Retrieval Orchestrator (PostgreSQL).",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(search_router)
