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

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

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
from knowledge_mining.mining.segmentation import DefaultSegmenter
from knowledge_mining.mining.enrich import RuleBasedEnricher
from knowledge_mining.mining.relations import DefaultRelationBuilder
from knowledge_mining.mining.snapshot import select_or_create_snapshot
from knowledge_mining.mining.publishing import assemble_build, classify_documents, publish_release
from knowledge_mining.mining.extractors import RuleBasedEntityExtractor, DefaultRoleClassifier  # noqa: F401 — used for enrich
from knowledge_mining.mining.pipeline import DocumentContext, PipelineConfig, MiningPipeline


def run(
    input_path: str | Path,
    *,
    asset_core_db_path: str | Path = "asset_core.sqlite",
    mining_runtime_db_path: str | Path = "mining_runtime.sqlite",
    batch_params: BatchParams | None = None,
    phase1_only: bool = False,
    publish_on_partial_failure: bool = False,
    llm_base_url: str | None = None,
    llm_bypass_proxy: bool = False,
) -> dict[str, Any]:
    """Execute the mining pipeline.

    Args:
        input_path: Directory to scan for documents
        asset_core_db_path: Path to asset_core.sqlite
        mining_runtime_db_path: Path to mining_runtime.sqlite
        batch_params: Batch-level configuration
        phase1_only: If True, stop after document-level processing (no build/publish)
        publish_on_partial_failure: If True, publish even when some docs failed.
            Default False: partial failures block active release, run marked "completed_with_errors".
        llm_base_url: LLM service URL (e.g. "http://localhost:8900"). None = no LLM.
        llm_bypass_proxy: If True, bypass system proxy for LLM calls (for corporate networks).

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

    # Pre-generate run_id so we can fail_run on global exception
    run_id = uuid.uuid4().hex

    # LLM integration: create question generator if URL provided
    question_generator = _init_llm(llm_base_url, llm_bypass_proxy)

    try:
        return _run_pipeline(
            asset_db, runtime_db, input_path, params, phase1_only, run_id,
            publish_on_partial_failure, question_generator,
        )
    except Exception as e:
        # Mark run as failed
        try:
            tracker = RuntimeTracker(runtime_db)
            tracker.fail_run(run_id, error_summary=str(e)[:500])
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

def _init_llm(llm_base_url: str | None, bypass_proxy: bool = False) -> dict[str, Any] | None:
    """Initialize LLM services if URL provided.

    Registers templates if llm_service is reachable.
    Returns dict with question_generator and enricher, or None.
    """
    if not llm_base_url:
        return None

    from knowledge_mining.mining.llm_client import LlmClient
    from knowledge_mining.mining.llm_templates import TEMPLATES
    from knowledge_mining.mining.retrieval_units import LlmQuestionGenerator

    client = LlmClient(base_url=llm_base_url, bypass_proxy=bypass_proxy)
    if not client.health_check():
        logger.warning("LLM service at %s unreachable, proceeding without LLM", llm_base_url)
        return None

    # Register templates (idempotent)
    for tpl in TEMPLATES:
        client.register_template(tpl)

    result: dict[str, Any] = {
        "question_generator": LlmQuestionGenerator(base_url=llm_base_url, bypass_proxy=bypass_proxy),
    }

    # v1.2: Try to create LlmEnricher if available
    try:
        from knowledge_mining.mining.enrich import LlmEnricher
        result["enricher"] = LlmEnricher(
            base_url=llm_base_url,
            fallback_enricher=RuleBasedEnricher(),
            bypass_proxy=bypass_proxy,
        )
    except (ImportError, Exception):
        pass

    return result


def _run_pipeline(
    asset_db: AssetCoreDB,
    runtime_db: MiningRuntimeDB,
    input_path: Path,
    params: BatchParams,
    phase1_only: bool,
    run_id: str,
    publish_on_partial_failure: bool = False,
    question_generator: Any = None,
) -> dict[str, Any]:
    """Core pipeline logic. Assumes DBs are already open."""
    tracker = RuntimeTracker(runtime_db)

    now = _utcnow()

    # Phase 1: Ingest
    docs, ingest_summary = ingest_directory(input_path, params)

    # Create batch in asset_core (before create_run so batch_id is available)
    batch_id = uuid.uuid4().hex

    tracker.create_run(MiningRunData(
        id=run_id,
        source_batch_id=batch_id,
        input_path=str(input_path),
        status="running",
        total_documents=len(docs),
        started_at=now,
        metadata_json={"ingest_summary": ingest_summary},
    ))
    runtime_db.commit()
    asset_db.upsert_source_batch(
        batch_id=batch_id,
        batch_code=f"batch-{run_id[:8]}",
        source_type=params.default_source_type,
        description=f"Mining run {run_id}",
    )
    asset_db.commit()

    # Build pipeline config with pluggable operators
    entity_extractor = RuleBasedEntityExtractor()
    role_classifier = DefaultRoleClassifier()
    enricher = RuleBasedEnricher(
        entity_extractor=entity_extractor,
        role_classifier=role_classifier,
    )

    pipeline_config = PipelineConfig(
        parser_factory=create_parser,
        segmenter=DefaultSegmenter(),
        enricher=enricher,
        relation_builder=DefaultRelationBuilder(),
        question_generator=question_generator,
    )
    pipeline = MiningPipeline(pipeline_config)

    committed_count = 0
    failed_count = 0
    skipped_count = 0
    snapshot_decisions: list[dict[str, Any]] = []

    for doc in docs:
        rd_id = uuid.uuid4().hex
        doc_key = f"doc:/{doc.relative_path}"

        # Determine action by comparing with existing document
        existing_doc = asset_db.get_document_by_key(doc_key)
        if existing_doc is None:
            action = "NEW"
        elif existing_doc["normalized_content_hash"] != doc.normalized_content_hash:
            action = "UPDATE"
        else:
            action = "SKIP"

        tracker.register_document(MiningRunDocumentData(
            id=rd_id,
            run_id=run_id,
            document_key=doc_key,
            raw_content_hash=doc.raw_content_hash,
            normalized_content_hash=doc.normalized_content_hash,
            action=action,
        ))
        runtime_db.commit()

        # SKIP: content unchanged, reuse existing snapshot without reprocessing
        if action == "SKIP" and existing_doc is not None:
            existing_link = asset_db._fetchone(
                "SELECT document_snapshot_id FROM asset_document_snapshot_links "
                "WHERE document_id = ? ORDER BY created_at DESC LIMIT 1",
                (existing_doc["id"],),
            )
            if existing_link:
                tracker.commit_document(rd_id, existing_doc["id"], existing_link["document_snapshot_id"])
                skipped_count += 1
                snapshot_decisions.append({
                    "document_id": existing_doc["id"],
                    "document_snapshot_id": existing_link["document_snapshot_id"],
                    "document_key": doc_key,
                })
                runtime_db.commit()
                continue

        try:
            profile = DocumentProfile(
                document_key=doc_key,
                source_type=doc.source_type or params.default_source_type,
                document_type=doc.document_type or params.default_document_type,
                scope_json=doc.scope_json,
                tags_json=doc.tags_json,
                title=doc.title,
            )

            # Build document context
            ctx = DocumentContext(raw_file=doc, profile=profile)

            # Stage tracking callback
            def _make_stage_cb(rd_id: str, run_id: str):
                import uuid as _uuid
                stage_events: dict[str, Any] = {}
                def cb(stage_name: str, current_ctx: DocumentContext):
                    evt = tracker.start_stage(run_id, stage_name, rd_id)
                    stage_events[stage_name] = evt
                def end_cb(stage_name: str, summary: str = ""):
                    evt = stage_events.get(stage_name)
                    if evt:
                        tracker.end_stage(evt, run_id, stage_name, output_summary=summary)
                        runtime_db.commit()
                return cb, end_cb

            stage_cb, stage_end = _make_stage_cb(rd_id, run_id)

            # Run pipeline
            ctx = pipeline.process_document(ctx, stage_callback=stage_cb)

            if ctx.tree is None:
                tracker.skip_document(rd_id)
                skipped_count += 1
                runtime_db.commit()
                continue

            # End stage tracking
            stage_end("parse", f"tree={'yes' if ctx.tree else 'no'}")
            stage_end("segment", f"{len(ctx.segments)} segments")
            stage_end("enrich", f"{len(ctx.segments)} enriched")
            stage_end("build_relations", f"{len(ctx.relations)} relations")
            stage_end("build_retrieval_units", f"{len(ctx.retrieval_units)} units")

            segments = list(ctx.segments)
            relations = list(ctx.relations)
            seg_id_map = ctx.seg_ids
            retrieval_units = list(ctx.retrieval_units)

            # Stage 6: Select/create snapshot
            evt = tracker.start_stage(run_id, "select_snapshot", rd_id)
            document_id, snapshot_id, link_id = select_or_create_snapshot(
                asset_db, doc, profile, batch_id=batch_id,
            )
            tracker.end_stage(evt, run_id, "select_snapshot")
            asset_db.commit()

            # v1.2 UPDATE cleanup: remove old snapshot data before writing new
            if action == "UPDATE" and existing_doc is not None:
                old_links = asset_db._fetchall(
                    "SELECT document_snapshot_id FROM asset_document_snapshot_links "
                    "WHERE document_id = ? ORDER BY created_at DESC",
                    (existing_doc["id"],),
                )
                # Skip the latest (just created), clean up older ones
                for old_link in old_links[1:] if len(old_links) > 1 else []:
                    old_snap_id = old_link["document_snapshot_id"]
                    asset_db.delete_retrieval_units_by_snapshot(old_snap_id)
                    asset_db.delete_relations_by_snapshot(old_snap_id)
                    asset_db.delete_segments_by_snapshot(old_snap_id)
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
                    source_segment_id=ru.source_segment_id,
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
                "document_key": doc_key,
            })

            runtime_db.commit()

        except Exception as e:
            tracker.fail_document(rd_id, str(e)[:500])
            failed_count += 1
            runtime_db.commit()

    # Phase 2: Build & Publish (unless phase1_only)
    build_id = None
    release_id = None
    has_failures = failed_count > 0

    # Build is always created if there are committed documents
    if not phase1_only and snapshot_decisions:
        # Classify documents: NEW/UPDATE/SKIP/REMOVE against previous active build
        snapshot_decisions = classify_documents(asset_db, snapshot_decisions)

        # Stage 7: Assemble build (auto-selects full vs incremental)
        evt = tracker.start_stage(run_id, "assemble_build")
        build_id = assemble_build(
            asset_db,
            run_id=run_id,
            batch_id=batch_id,
            snapshot_decisions=snapshot_decisions,
        )
        tracker.end_stage(evt, run_id, "assemble_build", output_summary=f"build_id={build_id}")
        asset_db.commit()
        runtime_db.commit()

        # Stage 8: Validate (already done inside assemble_build)
        evt = tracker.start_stage(run_id, "validate_build")
        tracker.end_stage(evt, run_id, "validate_build", output_summary="passed")
        runtime_db.commit()

        # Stage 9: Publish release — only if no failures or explicitly allowed
        if not has_failures or publish_on_partial_failure:
            evt = tracker.start_stage(run_id, "publish_release")
            release_id = publish_release(
                asset_db,
                build_id=build_id,
                released_by=f"run:{run_id}",
            )
            tracker.end_stage(evt, run_id, "publish_release", output_summary=f"release_id={release_id}")
            asset_db.commit()
            runtime_db.commit()

    # Determine final run status (use SQL-valid values only)
    run_status = "completed"

    tracker.complete_run(
        run_id,
        build_id=build_id,
        committed_count=committed_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        new_count=committed_count,
    )
    runtime_db.commit()

    return {
        "run_id": run_id,
        "status": run_status,
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
