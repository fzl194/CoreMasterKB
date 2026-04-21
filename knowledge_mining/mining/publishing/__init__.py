"""Publishing stage: build + release for v1.1.

Two-phase:
- assemble_build: select snapshots, merge with previous active build
- publish_release: activate a build as the current active release
"""
from __future__ import annotations

import uuid
from typing import Any

from knowledge_mining.mining.db import AssetCoreDB


def assemble_build(
    asset_db: AssetCoreDB,
    *,
    run_id: str,
    batch_id: str | None = None,
    build_mode: str = "full",
    snapshot_decisions: list[dict[str, Any]],
) -> str:
    """Assemble a new build from snapshot decisions.

    snapshot_decisions: list of dicts with keys:
        document_id, document_snapshot_id, reason (add/update/retain/remove),
        selection_status (active/removed)

    Returns build_id.
    """
    # Get previous active build for incremental merge
    parent_build_id = None
    prev_build = asset_db.get_active_build()
    if prev_build and build_mode == "incremental":
        parent_build_id = prev_build["id"]

    build_id = uuid.uuid4().hex
    build_code = f"B-{uuid.uuid4().hex[:8].upper()}"

    asset_db.insert_build(
        build_id=build_id,
        build_code=build_code,
        status="building",
        build_mode=build_mode,
        source_batch_id=batch_id,
        parent_build_id=parent_build_id,
        mining_run_id=run_id,
        summary_json={
            "snapshot_count": len([d for d in snapshot_decisions if d.get("selection_status") == "active"]),
            "removed_count": len([d for d in snapshot_decisions if d.get("selection_status") == "removed"]),
        },
    )

    # If incremental merge, carry forward parent build snapshots
    if parent_build_id and prev_build:
        parent_snapshots = asset_db.get_build_snapshots(parent_build_id)
        decided_doc_ids = {d["document_id"] for d in snapshot_decisions}
        for ps in parent_snapshots:
            if ps["document_id"] not in decided_doc_ids:
                asset_db.upsert_build_document_snapshot(
                    build_id=build_id,
                    document_id=ps["document_id"],
                    document_snapshot_id=ps["document_snapshot_id"],
                    selection_status="active",
                    reason="retain",
                )

    # Add new decisions
    for decision in snapshot_decisions:
        asset_db.upsert_build_document_snapshot(
            build_id=build_id,
            document_id=decision["document_id"],
            document_snapshot_id=decision["document_snapshot_id"],
            selection_status=decision.get("selection_status", "active"),
            reason=decision.get("reason", "add"),
        )

    # Validate and mark as validated
    asset_db.update_build_status(build_id, "validated")
    return build_id


def publish_release(
    asset_db: AssetCoreDB,
    build_id: str,
    *,
    channel: str = "default",
    released_by: str | None = None,
    release_notes: str | None = None,
) -> str:
    """Publish a validated build as the active release.

    Returns release_id.
    """
    build = asset_db.get_build(build_id)
    if build is None:
        raise ValueError(f"Build {build_id} not found")
    if build["status"] not in ("validated", "published"):
        raise ValueError(f"Build {build_id} status is {build['status']}, expected validated/published")

    # Get previous active release for chain
    prev_release = asset_db.get_active_release(channel)
    prev_release_id = prev_release["id"] if prev_release else None

    release_id = uuid.uuid4().hex
    release_code = f"R-{uuid.uuid4().hex[:8].upper()}"

    asset_db.insert_release(
        release_id=release_id,
        release_code=release_code,
        build_id=build_id,
        channel=channel,
        status="staging",
        previous_release_id=prev_release_id,
        released_by=released_by,
        release_notes=release_notes,
    )

    # Activate: retire old, activate new
    asset_db.activate_release(release_id)

    return release_id
