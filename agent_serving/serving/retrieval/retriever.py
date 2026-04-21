"""Abstract Retriever interface — v1.1 retrieval architecture.

All retrievers implement the same protocol so the search pipeline
can swap between BM25, vector, or hybrid without code changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from agent_serving.serving.schemas.models import QueryPlan, RetrievalCandidate


class Retriever(ABC):
    """Base class for retrieval strategies."""

    @abstractmethod
    async def retrieve(
        self,
        plan: QueryPlan,
        snapshot_ids: list[str],
    ) -> list[RetrievalCandidate]:
        """Return scored candidates from the index.

        Args:
            plan: query plan with keywords, entity/scope constraints.
            snapshot_ids: document snapshots in scope.

        Returns:
            Scored candidates sorted by descending relevance.
        """
        ...
