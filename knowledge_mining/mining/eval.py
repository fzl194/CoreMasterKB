"""Minimal evaluation runner for retrieval quality assessment.

Evaluates Recall@K against a domain pack's eval_questions by searching
retrieval_units in the asset database.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvalResult:
    """Result for a single eval question."""
    question_id: str
    question: str
    hit: bool
    recall_rank: int | None  # rank of first hit (1-based), None if miss
    matched_entities: list[str] = field(default_factory=list)
    evidence_found: bool = False


@dataclass(frozen=True)
class EvalReport:
    """Aggregate evaluation report."""
    domain_id: str
    total_questions: int
    recall_at_5: float
    recall_at_10: float
    per_question: tuple[EvalResult, ...]
    miss_count: int


def run_eval(
    profile: Any,
    asset_db_path: str,
    *,
    k: int = 5,
) -> EvalReport:
    """Run retrieval evaluation against a domain pack's eval_questions.

    For each eval question, searches retrieval_units using keyword matching
    and checks if expected entities/evidence appear in top-K results.

    Args:
        profile: DomainProfile with eval_questions.
        asset_db_path: Path to asset_core.sqlite.
        k: Number of top results to consider (default 5).

    Returns:
        EvalReport with Recall@K metrics.
    """
    from knowledge_mining.mining.db import AssetCoreDB
    from knowledge_mining.mining.text_utils import tokenize_for_search

    questions = profile.eval_questions
    if not questions:
        logger.warning("No eval questions in domain pack '%s'", profile.domain_id)
        return EvalReport(
            domain_id=profile.domain_id,
            total_questions=0,
            recall_at_5=0.0,
            recall_at_10=0.0,
            per_question=(),
            miss_count=0,
        )

    db = AssetCoreDB(asset_db_path)
    db.open()

    try:
        results: list[EvalResult] = []
        for q in questions:
            result = _evaluate_question(q, db, k)
            results.append(result)

        total = len(results)
        hits_5 = sum(1 for r in results if r.hit)
        hits_10 = sum(1 for r in results if r.recall_rank is not None and r.recall_rank <= 10)
        misses = sum(1 for r in results if not r.hit)

        return EvalReport(
            domain_id=profile.domain_id,
            total_questions=total,
            recall_at_5=hits_5 / total if total > 0 else 0.0,
            recall_at_10=hits_10 / total if total > 0 else 0.0,
            per_question=tuple(results),
            miss_count=misses,
        )
    finally:
        db.close()


def _evaluate_question(
    question: Any,
    db: Any,
    k: int = 5,
) -> EvalResult:
    """Evaluate a single question against retrieval units.

    Uses simple keyword search: tokenize question and check if
    retrieval_units contain expected entities/evidence in top results.
    """
    # Search using question text
    search_tokens = tokenize_for_search(question.question)
    if not search_tokens:
        return EvalResult(
            question_id=question.id,
            question=question.question,
            hit=False,
            recall_rank=None,
        )

    # Build FTS5 query from tokens
    fts_query = " ".join(f'"{t}"' for t in search_tokens[:5])  # limit to 5 tokens

    # Query retrieval units
    rows = db._fetchall(
        "SELECT unit_key, text, search_text, entity_refs_json "
        "FROM asset_retrieval_units "
        "WHERE asset_retrieval_units MATCH ? "
        "ORDER BY weight DESC LIMIT ?",
        (fts_query, max(k, 10)),
    )

    if not rows:
        return EvalResult(
            question_id=question.id,
            question=question.question,
            hit=False,
            recall_rank=None,
        )

    # Check hits
    expected_entities = set(question.expected_entities)
    expected_evidence = set(question.expected_evidence_contains)

    for rank, row in enumerate(rows, start=1):
        text = row["text"] or ""
        search_text = row["search_text"] or ""
        combined = f"{text} {search_text}".lower()

        # Check entity matches
        matched = [e for e in expected_entities if e.lower() in combined]

        # Check evidence matches
        evidence_found = all(
            e.lower() in combined for e in expected_evidence
        )

        if matched or evidence_found:
            hit = rank <= k
            return EvalResult(
                question_id=question.id,
                question=question.question,
                hit=hit,
                recall_rank=rank,
                matched_entities=matched,
                evidence_found=evidence_found,
            )

    return EvalResult(
        question_id=question.id,
        question=question.question,
        hit=False,
        recall_rank=None,
    )


def format_report(report: EvalReport) -> str:
    """Format an EvalReport as a human-readable string."""
    lines = [
        f"=== Eval Report: {report.domain_id} ===",
        f"Total questions: {report.total_questions}",
        f"Recall@5:  {report.recall_at_5:.1%}",
        f"Recall@10: {report.recall_at_10:.1%}",
        f"Misses: {report.miss_count}",
        "",
    ]

    for r in report.per_question:
        status = "HIT" if r.hit else "MISS"
        rank_str = f"rank={r.recall_rank}" if r.recall_rank else "not found"
        lines.append(f"  [{status}] {r.question_id}: {r.question[:50]}... ({rank_str})")

    return "\n".join(lines)
