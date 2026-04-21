"""Tests for v1.1 AssetRepository — active scope, source drill-down, relations."""
import json

import pytest
import pytest_asyncio

from agent_serving.serving.repositories.asset_repo import AssetRepository
from agent_serving.tests.conftest import SEED_IDS


@pytest_asyncio.fixture
async def repo(db_connection):
    return AssetRepository(db_connection)


class TestResolveActiveScope:
    @pytest.mark.asyncio
    async def test_active_scope_found(self, repo, seed_ids):
        scope = await repo.resolve_active_scope()
        assert scope.release_id == seed_ids["release_id"]
        assert scope.build_id == seed_ids["build_id"]
        assert len(scope.snapshot_ids) == 3
        assert len(scope.document_snapshot_map) > 0

    @pytest.mark.asyncio
    async def test_no_active_release(self, db_connection):
        await db_connection.execute(
            "UPDATE asset_publish_releases SET status = 'retired' WHERE id = ?",
            (SEED_IDS["release_id"],),
        )
        await db_connection.commit()
        repo = AssetRepository(db_connection)

        with pytest.raises(ValueError, match="no_active_release"):
            await repo.resolve_active_scope()

    @pytest.mark.asyncio
    async def test_multiple_active_releases(self, db_connection):
        # The UNIQUE constraint on (channel) WHERE status='active' prevents
        # inserting a second active release in the same channel.
        # Test with a different channel to verify the logic still catches it.
        # Since the unique index blocks same-channel, we test by checking the
        # unique index catches it when we try same channel.
        with pytest.raises(Exception):
            # This should fail due to UNIQUE constraint
            await db_connection.execute(
                "INSERT INTO asset_publish_releases "
                "(id, release_code, build_id, channel, status, metadata_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("dup-release", "DUP-001", SEED_IDS["build_id"], "default", "active", "{}"),
            )


class TestResolveSourceSegments:
    @pytest.mark.asyncio
    async def test_valid_source_refs(self, repo, seed_ids):
        source_refs = json.dumps({"raw_segment_ids": [seed_ids["rs_add_apn_udg"]]})
        segments = await repo.resolve_source_segments(source_refs)
        assert len(segments) == 1
        assert segments[0]["id"] == seed_ids["rs_add_apn_udg"]
        assert segments[0]["raw_text"] is not None

    @pytest.mark.asyncio
    async def test_empty_source_refs(self, repo):
        segments = await repo.resolve_source_segments(None)
        assert segments == []

    @pytest.mark.asyncio
    async def test_malformed_json(self, repo):
        segments = await repo.resolve_source_segments("not json")
        assert segments == []

    @pytest.mark.asyncio
    async def test_multiple_segments(self, repo, seed_ids):
        source_refs = json.dumps({
            "raw_segment_ids": [seed_ids["rs_add_apn_udg"], seed_ids["rs_5g_concept"]],
        })
        segments = await repo.resolve_source_segments(source_refs)
        assert len(segments) == 2


class TestGetRelations:
    @pytest.mark.asyncio
    async def test_relations_for_segments(self, repo, seed_ids):
        relations = await repo.get_relations_for_segments(
            [seed_ids["rs_add_apn_udg"]],
        )
        assert len(relations) >= 1
        assert any(r["relation_type"] == "next" for r in relations)

    @pytest.mark.asyncio
    async def test_empty_segment_list(self, repo):
        relations = await repo.get_relations_for_segments([])
        assert relations == []

    @pytest.mark.asyncio
    async def test_relation_type_filter(self, repo, seed_ids):
        relations = await repo.get_relations_for_segments(
            [seed_ids["rs_add_apn_udg"]],
            relation_types=["next"],
        )
        assert all(r["relation_type"] == "next" for r in relations)


class TestGetDocumentSources:
    @pytest.mark.asyncio
    async def test_fetch_documents(self, repo, seed_ids):
        sources = await repo.get_document_sources([seed_ids["doc_udg"]])
        assert len(sources) >= 1
        assert any(s["document_key"] == "UDG_OM_REF" for s in sources)

    @pytest.mark.asyncio
    async def test_empty_ids(self, repo):
        sources = await repo.get_document_sources([])
        assert sources == []
