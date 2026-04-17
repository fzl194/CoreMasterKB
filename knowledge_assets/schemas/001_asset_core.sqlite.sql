-- CoreMasterKB M1 Asset Core Schema v0.5 - SQLite dev mode
--
-- This file mirrors the PostgreSQL asset schema with SQLite-compatible
-- types and table names. Mining and Serving must use this shared dev DDL
-- instead of maintaining private SQLite copies.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS asset_source_batches (
    id              TEXT PRIMARY KEY,
    batch_code      TEXT NOT NULL UNIQUE,
    source_type     TEXT NOT NULL CHECK (
        source_type IN (
            'manual_upload',
            'folder_scan',
            'api_import',
            'official_vendor',
            'expert_authored',
            'user_import',
            'synthetic_coldstart',
            'other'
        )
    ),
    description     TEXT,
    created_by      TEXT,
    created_at      TEXT NOT NULL,
    metadata_json   TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS asset_publish_versions (
    id                      TEXT PRIMARY KEY,
    version_code            TEXT NOT NULL UNIQUE,
    status                  TEXT NOT NULL CHECK (status IN ('staging', 'active', 'archived', 'failed')),
    base_publish_version_id TEXT REFERENCES asset_publish_versions(id) ON DELETE SET NULL,
    source_batch_id         TEXT REFERENCES asset_source_batches(id) ON DELETE SET NULL,
    description             TEXT,
    build_started_at        TEXT NOT NULL,
    build_finished_at       TEXT,
    activated_at            TEXT,
    build_error             TEXT,
    metadata_json           TEXT NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_asset_publish_versions_one_active
    ON asset_publish_versions(status)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_asset_publish_versions_status
    ON asset_publish_versions(status);

CREATE INDEX IF NOT EXISTS idx_asset_publish_versions_base
    ON asset_publish_versions(base_publish_version_id);

CREATE INDEX IF NOT EXISTS idx_asset_publish_versions_source_batch
    ON asset_publish_versions(source_batch_id);

CREATE TABLE IF NOT EXISTS asset_raw_documents (
    id                      TEXT PRIMARY KEY,
    publish_version_id      TEXT NOT NULL REFERENCES asset_publish_versions(id) ON DELETE CASCADE,
    document_key            TEXT NOT NULL,
    source_uri              TEXT NOT NULL,
    relative_path           TEXT NOT NULL,
    file_name               TEXT NOT NULL,
    file_type               TEXT NOT NULL CHECK (file_type IN ('markdown', 'html', 'pdf', 'doc', 'docx', 'txt', 'other')),
    source_type             TEXT CHECK (
        source_type IS NULL OR
        source_type IN (
            'manual_upload',
            'folder_scan',
            'api_import',
            'official_vendor',
            'expert_authored',
            'user_import',
            'synthetic_coldstart',
            'other'
        )
    ),
    title                   TEXT,
    document_type           TEXT CHECK (
        document_type IS NULL OR
        document_type IN (
            'command',
            'feature',
            'procedure',
            'troubleshooting',
            'alarm',
            'constraint',
            'checklist',
            'expert_note',
            'project_note',
            'standard',
            'training',
            'reference',
            'other'
        )
    ),
    content_hash            TEXT NOT NULL,
    copied_from_document_id TEXT REFERENCES asset_raw_documents(id) ON DELETE SET NULL,
    origin_batch_id         TEXT REFERENCES asset_source_batches(id) ON DELETE SET NULL,
    created_at              TEXT NOT NULL,
    scope_json              TEXT NOT NULL DEFAULT '{}',
    tags_json               TEXT NOT NULL DEFAULT '[]',
    structure_quality       TEXT NOT NULL DEFAULT 'unknown' CHECK (
        structure_quality IN (
            'markdown_native',
            'plain_text_only',
            'full_html',
            'mixed',
            'unknown'
        )
    ),
    processing_profile_json TEXT NOT NULL DEFAULT '{}',
    metadata_json           TEXT NOT NULL DEFAULT '{}',
    UNIQUE (publish_version_id, document_key),
    UNIQUE (id, publish_version_id)
);

CREATE INDEX IF NOT EXISTS idx_asset_raw_documents_publish_version
    ON asset_raw_documents(publish_version_id);

CREATE INDEX IF NOT EXISTS idx_asset_raw_documents_origin_batch
    ON asset_raw_documents(origin_batch_id);

CREATE INDEX IF NOT EXISTS idx_asset_raw_documents_content_hash
    ON asset_raw_documents(publish_version_id, content_hash);

CREATE INDEX IF NOT EXISTS idx_asset_raw_documents_source_type
    ON asset_raw_documents(publish_version_id, source_type);

CREATE INDEX IF NOT EXISTS idx_asset_raw_documents_file_type
    ON asset_raw_documents(publish_version_id, file_type);

CREATE INDEX IF NOT EXISTS idx_asset_raw_documents_document_type
    ON asset_raw_documents(publish_version_id, document_type);

CREATE INDEX IF NOT EXISTS idx_asset_raw_documents_relative_path
    ON asset_raw_documents(publish_version_id, relative_path);

CREATE TABLE IF NOT EXISTS asset_raw_segments (
    id                     TEXT PRIMARY KEY,
    publish_version_id     TEXT NOT NULL REFERENCES asset_publish_versions(id) ON DELETE CASCADE,
    raw_document_id        TEXT NOT NULL,
    segment_key            TEXT NOT NULL,
    segment_index          INTEGER NOT NULL CHECK (segment_index >= 0),
    section_path           TEXT NOT NULL DEFAULT '[]',
    section_title          TEXT,
    block_type             TEXT NOT NULL DEFAULT 'unknown' CHECK (block_type IN ('paragraph', 'table', 'list', 'code', 'blockquote', 'html_table', 'raw_html', 'unknown')),
    semantic_role          TEXT NOT NULL DEFAULT 'unknown' CHECK (semantic_role IN ('concept', 'parameter', 'example', 'note', 'procedure_step', 'troubleshooting_step', 'constraint', 'alarm', 'checklist', 'unknown')),
    raw_text               TEXT NOT NULL,
    normalized_text        TEXT NOT NULL,
    content_hash           TEXT NOT NULL,
    normalized_hash        TEXT NOT NULL,
    token_count            INTEGER CHECK (token_count IS NULL OR token_count >= 0),
    copied_from_segment_id TEXT REFERENCES asset_raw_segments(id) ON DELETE SET NULL,
    structure_json         TEXT NOT NULL DEFAULT '{}',
    source_offsets_json    TEXT NOT NULL DEFAULT '{}',
    entity_refs_json       TEXT NOT NULL DEFAULT '[]',
    metadata_json          TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (raw_document_id, publish_version_id)
        REFERENCES asset_raw_documents(id, publish_version_id)
        ON DELETE CASCADE,
    UNIQUE (publish_version_id, raw_document_id, segment_key),
    UNIQUE (id, publish_version_id)
);

CREATE INDEX IF NOT EXISTS idx_asset_raw_segments_publish_document
    ON asset_raw_segments(publish_version_id, raw_document_id);

CREATE INDEX IF NOT EXISTS idx_asset_raw_segments_normalized_hash
    ON asset_raw_segments(publish_version_id, normalized_hash);

CREATE INDEX IF NOT EXISTS idx_asset_raw_segments_block_role
    ON asset_raw_segments(publish_version_id, block_type, semantic_role);

CREATE TABLE IF NOT EXISTS asset_canonical_segments (
    id                 TEXT PRIMARY KEY,
    publish_version_id TEXT NOT NULL REFERENCES asset_publish_versions(id) ON DELETE CASCADE,
    canonical_key      TEXT NOT NULL,
    block_type         TEXT NOT NULL DEFAULT 'unknown' CHECK (block_type IN ('paragraph', 'table', 'list', 'code', 'blockquote', 'html_table', 'raw_html', 'unknown')),
    semantic_role      TEXT NOT NULL DEFAULT 'unknown' CHECK (semantic_role IN ('concept', 'parameter', 'example', 'note', 'procedure_step', 'troubleshooting_step', 'constraint', 'alarm', 'checklist', 'unknown')),
    title              TEXT,
    canonical_text     TEXT NOT NULL,
    summary            TEXT,
    search_text        TEXT NOT NULL,
    entity_refs_json   TEXT NOT NULL DEFAULT '[]',
    scope_json         TEXT NOT NULL DEFAULT '{}',
    has_variants       INTEGER NOT NULL DEFAULT 0 CHECK (has_variants IN (0, 1)),
    variant_policy     TEXT NOT NULL DEFAULT 'none' CHECK (variant_policy IN ('none', 'prefer_latest', 'require_scope', 'require_disambiguation', 'manual_review')),
    quality_score      REAL CHECK (quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)),
    created_at         TEXT NOT NULL,
    metadata_json      TEXT NOT NULL DEFAULT '{}',
    UNIQUE (publish_version_id, canonical_key),
    UNIQUE (id, publish_version_id)
);

CREATE INDEX IF NOT EXISTS idx_asset_canonical_segments_block_role
    ON asset_canonical_segments(publish_version_id, block_type, semantic_role);

CREATE INDEX IF NOT EXISTS idx_asset_canonical_segments_variants
    ON asset_canonical_segments(publish_version_id, has_variants, variant_policy);

CREATE INDEX IF NOT EXISTS idx_asset_canonical_segments_search_text
    ON asset_canonical_segments(publish_version_id, search_text);

CREATE TABLE IF NOT EXISTS asset_canonical_segment_sources (
    id                   TEXT PRIMARY KEY,
    publish_version_id   TEXT NOT NULL REFERENCES asset_publish_versions(id) ON DELETE CASCADE,
    canonical_segment_id TEXT NOT NULL,
    raw_segment_id       TEXT NOT NULL,
    relation_type        TEXT NOT NULL CHECK (
        relation_type IN (
            'primary',
            'exact_duplicate',
            'normalized_duplicate',
            'near_duplicate',
            'scope_variant',
            'conflict_candidate'
        )
    ),
    is_primary           INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    priority             INTEGER NOT NULL DEFAULT 100 CHECK (priority >= 0),
    similarity_score     REAL CHECK (similarity_score IS NULL OR (similarity_score >= 0 AND similarity_score <= 1)),
    diff_summary         TEXT,
    metadata_json        TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (canonical_segment_id, publish_version_id)
        REFERENCES asset_canonical_segments(id, publish_version_id)
        ON DELETE CASCADE,
    FOREIGN KEY (raw_segment_id, publish_version_id)
        REFERENCES asset_raw_segments(id, publish_version_id)
        ON DELETE CASCADE,
    UNIQUE (canonical_segment_id, raw_segment_id)
);

CREATE INDEX IF NOT EXISTS idx_asset_sources_canonical
    ON asset_canonical_segment_sources(publish_version_id, canonical_segment_id);

CREATE INDEX IF NOT EXISTS idx_asset_sources_raw
    ON asset_canonical_segment_sources(publish_version_id, raw_segment_id);

CREATE INDEX IF NOT EXISTS idx_asset_sources_primary_priority
    ON asset_canonical_segment_sources(canonical_segment_id, is_primary, priority);

CREATE INDEX IF NOT EXISTS idx_asset_sources_relation_type
    ON asset_canonical_segment_sources(publish_version_id, relation_type);
