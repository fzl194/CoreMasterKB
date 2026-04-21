-- CoreMasterKB Asset Core Schema v1.1 - Generic SQL baseline
--
-- Notes:
-- 1. This file mirrors the SQLite contract semantically.
-- 2. It is kept as a relational baseline, but current local development
--    and contract verification are driven by 001_asset_core.sqlite.sql.
-- 3. Full-text search integration is implementation-specific and should
--    be adapted by the runtime database layer.

CREATE TABLE IF NOT EXISTS asset_source_batches (
    id            TEXT PRIMARY KEY,
    batch_code    TEXT NOT NULL UNIQUE,
    source_type   TEXT NOT NULL,
    description   TEXT,
    created_by    TEXT,
    created_at    TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS asset_publish_versions (
    id                      TEXT PRIMARY KEY,
    version_code            TEXT NOT NULL UNIQUE,
    status                  TEXT NOT NULL,
    base_publish_version_id TEXT REFERENCES asset_publish_versions(id) ON DELETE SET NULL,
    source_batch_id         TEXT REFERENCES asset_source_batches(id) ON DELETE SET NULL,
    description             TEXT,
    build_started_at        TEXT NOT NULL,
    build_finished_at       TEXT,
    activated_at            TEXT,
    build_error             TEXT,
    metadata_json           TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS asset_raw_documents (
    id                      TEXT PRIMARY KEY,
    document_key            TEXT NOT NULL UNIQUE,
    source_uri              TEXT NOT NULL,
    relative_path           TEXT NOT NULL,
    file_name               TEXT NOT NULL,
    file_type               TEXT NOT NULL,
    source_type             TEXT,
    title                   TEXT,
    document_type           TEXT,
    content_hash            TEXT NOT NULL,
    origin_batch_id         TEXT REFERENCES asset_source_batches(id) ON DELETE SET NULL,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    scope_json              TEXT NOT NULL DEFAULT '{}',
    tags_json               TEXT NOT NULL DEFAULT '[]',
    structure_quality       TEXT NOT NULL DEFAULT 'unknown',
    processing_profile_json TEXT NOT NULL DEFAULT '{}',
    metadata_json           TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS asset_batch_documents (
    batch_id       TEXT NOT NULL REFERENCES asset_source_batches(id) ON DELETE CASCADE,
    document_id    TEXT NOT NULL REFERENCES asset_raw_documents(id) ON DELETE CASCADE,
    content_hash   TEXT NOT NULL,
    discovered_at  TEXT NOT NULL,
    PRIMARY KEY (batch_id, document_id)
);

CREATE TABLE IF NOT EXISTS asset_raw_segments (
    id                  TEXT PRIMARY KEY,
    raw_document_id     TEXT NOT NULL REFERENCES asset_raw_documents(id) ON DELETE CASCADE,
    segment_key         TEXT NOT NULL,
    segment_index       INTEGER NOT NULL,
    section_path        TEXT NOT NULL DEFAULT '[]',
    section_title       TEXT,
    block_type          TEXT NOT NULL DEFAULT 'unknown',
    semantic_role       TEXT NOT NULL DEFAULT 'unknown',
    raw_text            TEXT NOT NULL,
    normalized_text     TEXT NOT NULL,
    content_hash        TEXT NOT NULL,
    normalized_hash     TEXT NOT NULL,
    token_count         INTEGER,
    structure_json      TEXT NOT NULL DEFAULT '{}',
    source_offsets_json TEXT NOT NULL DEFAULT '{}',
    entity_refs_json    TEXT NOT NULL DEFAULT '[]',
    metadata_json       TEXT NOT NULL DEFAULT '{}',
    UNIQUE (raw_document_id, segment_key)
);

CREATE TABLE IF NOT EXISTS asset_raw_segment_relations (
    id                 TEXT PRIMARY KEY,
    source_segment_id  TEXT NOT NULL REFERENCES asset_raw_segments(id) ON DELETE CASCADE,
    target_segment_id  TEXT NOT NULL REFERENCES asset_raw_segments(id) ON DELETE CASCADE,
    relation_type      TEXT NOT NULL,
    weight             DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    confidence         DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    distance           INTEGER,
    metadata_json      TEXT NOT NULL DEFAULT '{}',
    UNIQUE (source_segment_id, target_segment_id, relation_type)
);

CREATE TABLE IF NOT EXISTS asset_retrieval_units (
    id                   TEXT PRIMARY KEY,
    unit_key             TEXT NOT NULL,
    unit_type            TEXT NOT NULL,
    target_type          TEXT NOT NULL,
    target_id            TEXT,
    raw_document_id      TEXT NOT NULL REFERENCES asset_raw_documents(id) ON DELETE CASCADE,
    title                TEXT,
    text                 TEXT NOT NULL,
    search_text          TEXT NOT NULL,
    block_type           TEXT NOT NULL DEFAULT 'unknown',
    semantic_role        TEXT NOT NULL DEFAULT 'unknown',
    facets_json          TEXT NOT NULL DEFAULT '{}',
    entity_refs_json     TEXT NOT NULL DEFAULT '[]',
    source_refs_json     TEXT NOT NULL DEFAULT '{}',
    llm_result_refs_json TEXT NOT NULL DEFAULT '{}',
    weight               DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    created_at           TEXT NOT NULL,
    metadata_json        TEXT NOT NULL DEFAULT '{}',
    UNIQUE (raw_document_id, unit_key)
);

CREATE TABLE IF NOT EXISTS asset_retrieval_embeddings (
    id                 TEXT PRIMARY KEY,
    retrieval_unit_id  TEXT NOT NULL REFERENCES asset_retrieval_units(id) ON DELETE CASCADE,
    embedding_model    TEXT NOT NULL,
    embedding_provider TEXT NOT NULL,
    text_kind          TEXT NOT NULL,
    embedding_dim      INTEGER NOT NULL,
    embedding_vector   TEXT NOT NULL,
    content_hash       TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    metadata_json      TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS asset_canonical_segments (
    id                 TEXT PRIMARY KEY,
    canonical_key      TEXT NOT NULL UNIQUE,
    block_type         TEXT NOT NULL DEFAULT 'unknown',
    semantic_role      TEXT NOT NULL DEFAULT 'unknown',
    title              TEXT,
    canonical_text     TEXT NOT NULL,
    summary            TEXT,
    search_text        TEXT NOT NULL,
    entity_refs_json   TEXT NOT NULL DEFAULT '[]',
    scope_json         TEXT NOT NULL DEFAULT '{}',
    has_variants       INTEGER NOT NULL DEFAULT 0,
    variant_policy     TEXT NOT NULL DEFAULT 'none',
    quality_score      DOUBLE PRECISION,
    created_at         TEXT NOT NULL,
    metadata_json      TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS asset_canonical_segment_sources (
    id                   TEXT PRIMARY KEY,
    canonical_segment_id TEXT NOT NULL REFERENCES asset_canonical_segments(id) ON DELETE CASCADE,
    raw_segment_id       TEXT NOT NULL REFERENCES asset_raw_segments(id) ON DELETE CASCADE,
    relation_type        TEXT NOT NULL,
    is_primary           INTEGER NOT NULL DEFAULT 0,
    priority             INTEGER NOT NULL DEFAULT 100,
    similarity_score     DOUBLE PRECISION,
    diff_summary         TEXT,
    metadata_json        TEXT NOT NULL DEFAULT '{}',
    UNIQUE (canonical_segment_id, raw_segment_id)
);

CREATE INDEX IF NOT EXISTS idx_asset_publish_versions_status
    ON asset_publish_versions(status);

CREATE INDEX IF NOT EXISTS idx_asset_raw_documents_origin_batch
    ON asset_raw_documents(origin_batch_id);

CREATE INDEX IF NOT EXISTS idx_asset_batch_documents_document
    ON asset_batch_documents(document_id);

CREATE INDEX IF NOT EXISTS idx_asset_raw_segments_document
    ON asset_raw_segments(raw_document_id);

CREATE INDEX IF NOT EXISTS idx_asset_raw_segment_relations_source
    ON asset_raw_segment_relations(source_segment_id, relation_type);

CREATE INDEX IF NOT EXISTS idx_asset_retrieval_units_document
    ON asset_retrieval_units(raw_document_id);

CREATE INDEX IF NOT EXISTS idx_asset_retrieval_embeddings_unit
    ON asset_retrieval_embeddings(retrieval_unit_id);

CREATE INDEX IF NOT EXISTS idx_asset_canonical_segment_sources_canonical
    ON asset_canonical_segment_sources(canonical_segment_id);
