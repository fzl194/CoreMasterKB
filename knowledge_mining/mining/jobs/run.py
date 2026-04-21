"""v1.1 Mining pipeline orchestrator.

Two entry points:
- run(input_path, phase1_only=False): full or phase1-only pipeline
- publish(run_id): publish a completed run's build

Pipeline stages per document:
  ingest -> parse -> segment -> enrich -> build_relations -> build_retrieval_units

Global stages:
  select_snapshot -> assemble_build -> [publish_release]
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge_mining.mining.db import AssetCoreDB, MiningRuntimeDB
from knowledge_mining.mining.models import (
    BatchParams,
    DocumentProfile,
    MiningRunData,
    MiningRunDocumentData,
    RawSegmentData,
    SegmentRelationData,
    RetrievalUnitData,
)
from knowledge_mining.mining.runtime import RuntimeTracker
from knowledge_mining.mining.ingestion import ingest_directory
from knowledge_mining.mining.parsers import create_parser
from knowledge_mining.mining.segmentation import segment_document
from knowledge_mining.mining.enrich import enrich_segments
from knowledge_mining.mining.relations import build_relations
from knowledge_mining.mining.retrieval_units import build_retrieval_units
from knowledge_mining.mining.snapshot import select_or_create_snapshot
from knowledge_mining.mining.publishing import assemble_build, publish_release
from knowledge_mining.mining.extractors import RuleBasedEntityExtractor, DefaultRoleClassifier


def run(
    input_path: str | Path,
    *,
    asset_core_db_path: str | Path = "asset_core.sqlite",
    mining_runtime_db_path: str | Path = "mining_runtime.sqlite",
    batch_params: BatchParams | None = None,
    phase1_only: bool = False,
) -> dict[str, Any]:
    """Execute the mining pipeline.

    Args:
        input_path: Directory to scan for documents
        asset_core_db_path: Path to asset_core.sqlite
        mining_runtime_db_path: Path to mining_runtime.sqlite
        batch_params: Batch-level configuration
        phase1_only: If True, stop after document-level processing (no build/publish)

    Returns:
        Summary dict with run_id, counts, and status.
    """
    input_path = Path(input_path)
    batch_params = batch_params or BatchParams()
    params = batch_params

    # Open databases
    asset_db = AssetCoreDB(asset_core_db_path)
    runtime_db = MiningRuntimeDB(mining_runtime_db_path)
    asset_db.open()
    runtime_db.open()

    try:
        return _run_pipeline(
            asset_db, runtime_db, input_path, params, phase1_only,
        )
    except Exception as e:
        # Attempt to mark run as failed if possible
        try:
            runtime_db.commit()
        except Exception:
            pass
        raise
    finally:
        asset_db.close()
        runtime_db.close()


def publish(
    run_id: str,
    *,
    asset_core_db_path: str | Path = "asset_core.sqlite",
    mining_runtime_db_path: str | Path = "mining_runtime.sqlite",
    channel: str = "default",
    released_by: str | None = None,
) -> dict[str, Any]:
    """Publish a completed run's build as an active release."""
    asset_db = AssetCoreDB(asset_core_db_path)
    runtime_db = MiningRuntimeDB(mining_runtime_db_path)
    asset_db.open()
    runtime_db.open()

    try:
        run_data = runtime_db.get_run(run_id)
        if run_data is None:
            raise ValueError(f"Run {run_id} not found")
        if run_data["status"] != "completed":
            raise ValueError(f"Run {run_id} status is {run_data['status']}, expected completed")
        build_id = run_data["build_id"]
        if not build_id:
            raise ValueError(f"Run {run_id} has no build_id")

        release_id = publish_release(
            asset_db,
            build_id=build_id,
            channel=channel,
            released_by=released_by,
            release_notes=f"Published from run {run_id}",
        )
        runtime_db.commit()
        asset_db.commit()

        return {"run_id": run_id, "build_id": build_id, "release_id": release_id}
    finally:
        asset_db.close()
        runtime_db.close()


# ===================================================================
# Internal pipeline implementation
# ===================================================================

def _run_pipeline(
    asset_db: AssetCoreDB,
    runtime_db: MiningRuntimeDB,
    input_path: Path,
    params: BatchParams,
    phase1_only: bool,
) -> dict[str, Any]:
    """Core pipeline logic. Assumes DBs are already open."""
    tracker = RuntimeTracker(runtime_db)

    # Create run
    run_id = uuid.uuid4().hex
    now = _utcnow()

    # Phase 1: Ingest
    docs, ingest_summary = ingest_directory(input_path, params)

    tracker.create_run(MiningRunData(
        id=run_id,
        input_path=str(input_path),
        status="running",
        total_documents=len(docs),
        started_at=now,
        metadata_json={"ingest_summary": ingest_summary},
    ))
    runtime_db.commit()

    # Create batch in asset_core
    batch_id = uuid.uuid4().hex
    asset_db.upsert_source_batch(
        batch_id=batch_id,
        batch_code=f"batch-{run_id[:8]}",
        source_type=params.default_source_type,
        description=f"Mining run {run_id}",
    )
    asset_db.commit()

    # Process each document
    entity_extractor = RuleBasedEntityExtractor()
    role_classifier = DefaultRoleClassifier()

    committed_count = 0
    failed_count = 0
    skipped_count = 0
    snapshot_decisions: list[dict[str, Any]] = []

    for doc in docs:
        rd_id = uuid.uuid4().hex
        doc_key = f"doc:/{doc.relative_path}"

        tracker.register_document(MiningRunDocumentData(
            id=rd_id,
            run_id=run_id,
            document_key=doc_key,
            raw_content_hash=doc.raw_content_hash,
            normalized_content_hash=doc.normalized_content_hash,
            action="NEW",
        ))
        runtime_db.commit()

        try:
            profile = DocumentProfile(
                document_key=doc_key,
                source_type=doc.source_type or params.default_source_type,
                document_type=doc.document_type or params.default_document_type,
                scope_json=doc.scope_json,
                tags_json=doc.tags_json,
                title=doc.title,
            )

            # Stage 1: Parse
            evt = tracker.start_stage(run_id, "parse", rd_id)
            parser = create_parser(doc.file_type)
            tree = parser.parse(doc.content, doc.file_name, {})
            tracker.end_stage(evt, run_id, "parse", output_summary=f"tree={'yes' if tree else 'no'}")
            runtime_db.commit()

            if tree is None:
                tracker.skip_document(rd_id)
                skipped_count += 1
                runtime_db.commit()
                continue

            # Stage 2: Segment
            evt = tracker.start_stage(run_id, "segment", rd_id)
            segments = segment_document(
                tree, profile,
                role_classifier=role_classifier,
                entity_extractor=entity_extractor,
                parser_name=doc.file_type,
            )
            tracker.end_stage(evt, run_id, "segment", output_summary=f"{len(segments)} segments")
            runtime_db.commit()

            # Stage 3: Enrich
            evt = tracker.start_stage(run_id, "enrich", rd_id)
            segments = enrich_segments(segments)
            tracker.end_stage(evt, run_id, "enrich", output_summary=f"{len(segments)} enriched")
            runtime_db.commit()

            # Stage 4: Build relations
            evt = tracker.start_stage(run_id, "build_relations", rd_id)
            relations, seg_id_map = build_relations(segments)
            tracker.end_stage(evt, run_id, "build_relations", output_summary=f"{len(relations)} relations")
            runtime_db.commit()

            # Stage 5: Build retrieval units
            evt = tracker.start_stage(run_id, "build_retrieval_units", rd_id)
            retrieval_units = build_retrieval_units(segments, document_key=doc_key)
            tracker.end_stage(evt, run_id, "build_retrieval_units", output_summary=f"{len(retrieval_units)} units")
            runtime_db.commit()

            # Stage 6: Select/create snapshot
            evt = tracker.start_stage(run_id, "select_snapshot", rd_id)
            document_id, snapshot_id, link_id = select_or_create_snapshot(
                asset_db, doc, profile, batch_id=batch_id,
            )
            tracker.end_stage(evt, run_id, "select_snapshot")
            asset_db.commit()

            # Write segments to DB
            for seg in segments:
                seg_key = f"{seg.document_key}#{seg.segment_index}"
                seg_id = seg_id_map.get(seg_key, uuid.uuid4().hex)
                asset_db.insert_raw_segment(
                    segment_id=seg_id,
                    document_snapshot_id=snapshot_id,
                    segment_key=seg_key,
                    segment_index=seg.segment_index,
                    block_type=seg.block_type,
                    semantic_role=seg.semantic_role,
                    section_path=seg.section_path,
                    section_title=seg.section_title,
                    raw_text=seg.raw_text,
                    normalized_text=seg.normalized_text,
                    content_hash=seg.content_hash,
                    normalized_hash=seg.normalized_hash,
                    token_count=seg.token_count,
                    structure_json=seg.structure_json,
                    source_offsets_json=seg.source_offsets_json,
                    entity_refs_json=seg.entity_refs_json,
                    metadata_json=seg.metadata_json,
                )

            # Write relations to DB
            for rel in relations:
                src_id = seg_id_map.get(rel.source_segment_key, "")
                tgt_id = seg_id_map.get(rel.target_segment_key, "")
                if src_id and tgt_id:
                    asset_db.insert_segment_relation(
                        relation_id=uuid.uuid4().hex,
                        document_snapshot_id=snapshot_id,
                        source_segment_id=src_id,
                        target_segment_id=tgt_id,
                        relation_type=rel.relation_type,
                        weight=rel.weight,
                        confidence=rel.confidence,
                        distance=rel.distance,
                        metadata_json=rel.metadata_json,
                    )

            # Write retrieval units to DB
            for ru in retrieval_units:
                asset_db.insert_retrieval_unit(
                    unit_id=uuid.uuid4().hex,
                    document_snapshot_id=snapshot_id,
                    unit_key=ru.unit_key,
                    unit_type=ru.unit_type,
                    target_type=ru.target_type,
                    target_ref_json=ru.target_ref_json,
                    title=ru.title,
                    text=ru.text,
                    search_text=ru.search_text,
                    block_type=ru.block_type,
                    semantic_role=ru.semantic_role,
                    facets_json=ru.facets_json,
                    entity_refs_json=ru.entity_refs_json,
                    source_refs_json=ru.source_refs_json,
                    llm_result_refs_json=ru.llm_result_refs_json,
                    weight=ru.weight,
                    metadata_json=ru.metadata_json,
                )

            asset_db.commit()

            # Commit document
            tracker.commit_document(rd_id, document_id, snapshot_id)
            committed_count += 1

            snapshot_decisions.append({
                "document_id": document_id,
                "document_snapshot_id": snapshot_id,
                "selection_status": "active",
                "reason": "add",
            })

            runtime_db.commit()

        except Exception as e:
            tracker.fail_document(rd_id, str(e)[:500])
            failed_count += 1
            runtime_db.commit()

    # Phase 2: Build & Publish (unless phase1_only)
    build_id = None
    release_id = None

    if not phase1_only and snapshot_decisions:
        # Stage 7: Assemble build
        evt = tracker.start_stage(run_id, "assemble_build")
        build_id = assemble_build(
            asset_db,
            run_id=run_id,
            batch_id=batch_id,
            build_mode="full",
            snapshot_decisions=snapshot_decisions,
        )
        tracker.end_stage(evt, run_id, "assemble_build", output_summary=f"build_id={build_id}")
        asset_db.commit()
        runtime_db.commit()

        # Stage 8: Validate (already done inside assemble_build)
        evt = tracker.start_stage(run_id, "validate_build")
        tracker.end_stage(evt, run_id, "validate_build", output_summary="passed")
        runtime_db.commit()

        # Stage 9: Publish release
        evt = tracker.start_stage(run_id, "publish_release")
        release_id = publish_release(
            asset_db,
            build_id=build_id,
            released_by=f"run:{run_id}",
        )
        tracker.end_stage(evt, run_id, "publish_release", output_summary=f"release_id={release_id}")
        asset_db.commit()
        runtime_db.commit()

    # Complete run
    tracker.complete_run(
        run_id,
        committed_count=committed_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        new_count=committed_count,
        build_id=build_id,
    )
    runtime_db.commit()

    return {
        "run_id": run_id,
        "status": "completed",
        "total_documents": len(docs),
        "committed_count": committed_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "build_id": build_id,
        "release_id": release_id,
    }


def _utcnow() -> str:
    from datetime import timezone
    return datetime.now(timezone.utc).isoformat()
