"""DenseVectorRetriever — pgvector cosine distance retrieval.

Uses pgvector's <=> operator for efficient nearest-neighbor search
over the asset_retrieval_embeddings.embedding_vector_vec column.
No numpy dependency; no client-side caching needed — PG handles it.
"""
from __future__ import annotations

import logging
from typing import Any

from psycopg_pool import AsyncConnectionPool

from agent_serving.serving.schemas.constants import ROUTE_DENSE_VECTOR
from agent_serving.serving.schemas.models import (
    RetrievalCandidate,
    RetrievalQuery,
    ScoreChain,
)
from agent_serving.serving.retrieval.retriever import Retriever

logger = logging.getLogger(__name__)


class DenseVectorRetriever(Retriever):
    """Dense vector retrieval using pgvector cosine distance."""

    def __init__(
        self,
        pool: AsyncConnectionPool,
        embedding_dimensions: int = 1024,
    ) -> None:
        self._pool = pool
        self._dimensions = embedding_dimensions

    async def retrieve(
        self,
        query: RetrievalQuery,
        snapshot_ids: list[str],
        top_k: int = 50,
    ) -> list[RetrievalCandidate]:
        """Retrieve by query embedding vector via pgvector.

        If query.query_embedding is None, auto-skip (return []).
        """
        if not snapshot_ids or not query.query_embedding:
            return []

        placeholders = ",".join("%s" for _ in snapshot_ids)
        vec_literal = "[" + ",".join(str(v) for v in query.query_embedding) + "]"

        # Scope/filter pushdown
        scope_filter = self._build_scope_filter(query.scope)

        sql = f"""
            SELECT
                e.retrieval_unit_id,
                (e.embedding_vector_vec <=> %s::vector({self._dimensions})) AS distance,
                ru.id,
                ru.document_snapshot_id,
                ru.text,
                ru.title,
                ru.block_type,
                ru.semantic_role,
                ru.source_refs_json,
                ru.facets_json,
                ru.target_type,
                ru.target_ref_json,
                ru.unit_type,
                ru.source_segment_id
            FROM asset_retrieval_embeddings e
            JOIN asset_retrieval_units ru ON ru.id = e.retrieval_unit_id
            WHERE ru.document_snapshot_id IN ({placeholders})
              AND e.embedding_vector_vec IS NOT NULL
              {scope_filter}
            ORDER BY distance ASC
            LIMIT %s
        """
        params: list[Any] = [vec_literal, *snapshot_ids, top_k]

        try:
            async with self._pool.connection() as conn:
                cursor = await conn.execute(sql, params)
                rows = await cursor.fetchall()
        except Exception:
            logger.warning("pgvector query failed", exc_info=True)
            return []

        candidates = []
        for row in rows:
            r = dict(row)
            distance = r.get("distance", 1.0) or 1.0
            score = max(1.0 - distance, 0.0)
            candidates.append(RetrievalCandidate(
                retrieval_unit_id=r["retrieval_unit_id"],
                score=score,
                source=ROUTE_DENSE_VECTOR,
                metadata={
                    "document_snapshot_id": r.get("document_snapshot_id"),
                    "title": r.get("title"),
                    "block_type": r.get("block_type", "unknown"),
                    "semantic_role": r.get("semantic_role", "unknown"),
                    "text": r.get("text", ""),
                    "source_refs_json": r.get("source_refs_json", "{}"),
                    "facets_json": r.get("facets_json", "{}"),
                    "target_type": r.get("target_type", ""),
                    "target_ref_json": r.get("target_ref_json", "{}"),
                    "unit_type": r.get("unit_type", ""),
                    "source_segment_id": r.get("source_segment_id"),
                },
                score_chain=ScoreChain(
                    raw_score=score,
                    route_sources=[ROUTE_DENSE_VECTOR],
                ),
            ))
        return candidates

    @staticmethod
    def _build_scope_filter(scope: dict) -> str:
        """Build SQL filter from query scope for facets_json pushdown."""
        if not scope:
            return ""
        conditions = []
        for key, values in scope.items():
            if isinstance(values, list) and values:
                conditions.append(
                    f"ru.facets_json @> '{{\"{key}\": {values!r}}}'::jsonb"
                )
        return " AND " + " AND ".join(conditions) if conditions else ""
