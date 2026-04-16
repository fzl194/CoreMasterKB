"""FastAPI application with SQLite dev mode and DB injection."""
from __future__ import annotations

from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI, Request

from agent_serving.serving.api.health import router as health_router
from agent_serving.serving.api.search import router as search_router
from agent_serving.serving.repositories.asset_repo import AssetRepository
from agent_serving.serving.repositories.schema_adapter import create_asset_tables_sqlite


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await create_asset_tables_sqlite(db)
    app.state.db = db
    yield
    await db.close()


def get_repo(request: Request) -> AssetRepository:
    return AssetRepository(request.app.state.db)


app = FastAPI(
    title="Cloud Core Knowledge Backend",
    version="0.1.0",
    description="Agent Knowledge Backend for cloud core network.",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(search_router)
