-- CoreMasterKB Asset Core Schema v1.1 - SQLite
--
-- Current policy:
-- 1. Asset tables store only current active assets.
-- 2. asset_publish_versions is publish-control metadata, not per-row version ownership.
-- 3. Retrieval path: raw_documents -> raw_segments -> raw_segment_relations -> retrieval_units.
-- 4. canonical tables are retained only as non-primary compatibility tables.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS asset_source_batches (
    id            TEXT PRIMARY KEY,
    batch_code    TEXT NOT NULL UNIQUE,
    source_type   TEXT NOT NULL CHECK (
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
    description   TEXT,
    created_by    TEXT,
    created_at    TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
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

CREATE INDEX IF NOT EXISTS idx_asset_publish_versions_source_batch
    ON asset_publish_versions(source_batch_id);

CREATE TABLE IF NOT EXISTS asset_raw_documents (
    id                      TEXT PRIMARY KEY,
    document_key            TEXT NOT NULL UNIQUE,
    source_uri              TEXT NOT NULL,
    relative_path           TEXT NOT NULL,
    file_name               TEXT NOT NULL,
    file_type               TEXT NOT NULL CHECK (
        file_type IN ('markdown', 'html', 'pdf', 'doc', 'docx', 'txt', 'other')
    ),
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
    origin_batch_id         TEXT REFERENCES asset_source_batches(id) ON DELETE SET NULL,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
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
    metadata_json           TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_asset_raw_documents_origin_batch
    ON asset_raw_documents(origin_batch_id);

CREATE INDEX IF NOT EXISTS idx_asset_raw_documents_content_hash
    ON asset_raw_documents(content_hash);

CREATE INDEX IF NOT EXISTS idx_asset_raw_documents_relative_path
    ON asset_raw_documents(relative_path);

CREATE INDEX IF NOT EXISTS idx_asset_raw_documents_file_type
    ON asset_raw_documents(file_type);

CREATE INDEX IF NOT EXISTS idx_asset_raw_documents_document_type
    ON asset_raw_documents(document_type);

CREATE TABLE IF NOT EXISTS asset_batch_documents (
    batch_id       TEXT NOT NULL REFERENCES asset_source_batches(id) ON DELETE CASCADE,
    document_id    TEXT NOT NULL REFERENCES asset_raw_documents(id) ON DELETE CASCADE,
    content_hash   TEXT NOT NULL,
    discovered_at  TEXT NOT NULL,
    PRIMARY KEY (batch_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_asset_batch_documents_document
    ON asset_batch_documents(document_id);

CREATE TABLE IF NOT EXISTS asset_raw_segments (
    id                  TEXT PRIMARY KEY,
    raw_document_id     TEXT NOT NULL REFERENCES asset_raw_documents(id) ON DELETE CASCADE,
    segment_key         TEXT NOT NULL,
    segment_index       INTEGER NOT NULL CHECK (segment_index >= 0),
    section_path        TEXT NOT NULL DEFAULT '[]',
    section_title       TEXT,
    block_type          TEXT NOT NULL DEFAULT 'unknown' CHECK (
        block_type IN ('paragraph', 'heading', 'table', 'list', 'code', 'blockquote', 'html_table', 'raw_html', 'unknown')
    ),
    semantic_role       TEXT NOT NULL DEFAULT 'unknown' CHECK (
        semantic_role IN (
            'concept',
            'parameter',
            'example',
            'note',
            'procedure_step',
            'troubleshooting_step',
            'constraint',
            'alarm',
            'checklist',
            'unknown'
        )
    ),
    raw_text            TEXT NOT NULL,
    normalized_text     TEXT NOT NULL,
    content_hash        TEXT NOT NULL,
    normalized_hash     TEXT NOT NULL,
    token_count         INTEGER CHECK (token_count IS NULL OR token_count >= 0),
    structure_json      TEXT NOT NULL DEFAULT '{}',
    source_offsets_json TEXT NOT NULL DEFAULT '{}',
    entity_refs_json    TEXT NOT NULL DEFAULT '[]',
    metadata_json       TEXT NOT NULL DEFAULT '{}',
    UNIQUE (raw_document_id, segment_key)
);

CREATE INDEX IF NOT EXISTS idx_asset_raw_segments_document
    ON asset_raw_segments(raw_document_id);

CREATE INDEX IF NOT EXISTS idx_asset_raw_segments_document_index
    ON asset_raw_segments(raw_document_id, segment_index);

CREATE INDEX IF NOT EXISTS idx_asset_raw_segments_normalized_hash
    ON asset_raw_segments(normalized_hash);

CREATE INDEX IF NOT EXISTS idx_asset_raw_segments_block_role
    ON asset_raw_segments(block_type, semantic_role);

CREATE TABLE IF NOT EXISTS asset_raw_segment_relations (
    id                 TEXT PRIMARY KEY,
    source_segment_id  TEXT NOT NULL REFERENCES asset_raw_segments(id) ON DELETE CASCADE,
    target_segment_id  TEXT NOT NULL REFERENCES asset_raw_segments(id) ON DELETE CASCADE,
    relation_type      TEXT NOT NULL CHECK (
        relation_type IN (
            'previous',
            'next',
            'same_section',
            'same_parent_section',
            'section_header_of',
            'references',
            'elaborates',
            'condition',
            'contrast',
            'other'
        )
    ),
    weight             REAL NOT NULL DEFAULT 1.0,
    confidence         REAL NOT NULL DEFAULT 1.0,
    distance           INTEGER,
    metadata_json      TEXT NOT NULL DEFAULT '{}',
    UNIQUE (source_segment_id, target_segment_id, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_asset_raw_segment_relations_source
    ON asset_raw_segment_relations(source_segment_id, relation_type);

CREATE INDEX IF NOT EXISTS idx_asset_raw_segment_relations_target
    ON asset_raw_segment_relations(target_segment_id, relation_type);

CREATE TABLE IF NOT EXISTS asset_retrieval_units (
    id                   TEXT PRIMARY KEY,
    unit_key             TEXT NOT NULL,
    unit_type            TEXT NOT NULL CHECK (
        unit_type IN (
            'raw_text',
            'contextual_text',
            'summary',
            'generated_question',
            'entity_card',
            'table_row',
            'other'
        )
    ),
    target_type          TEXT NOT NULL CHECK (
        target_type IN ('raw_segment', 'section', 'document', 'entity', 'synthetic', 'other')
    ),
    target_id            TEXT,
    raw_document_id      TEXT NOT NULL REFERENCES asset_raw_documents(id) ON DELETE CASCADE,
    title                TEXT,
    text                 TEXT NOT NULL,
    search_text          TEXT NOT NULL,
    block_type           TEXT NOT NULL DEFAULT 'unknown' CHECK (
        block_type IN ('paragraph', 'heading', 'table', 'list', 'code', 'blockquote', 'html_table', 'raw_html', 'unknown')
    ),
    semantic_role        TEXT NOT NULL DEFAULT 'unknown' CHECK (
        semantic_role IN (
            'concept',
            'parameter',
            'example',
            'note',
            'procedure_step',
            'troubleshooting_step',
            'constraint',
            'alarm',
            'checklist',
            'unknown'
        )
    ),
    facets_json          TEXT NOT NULL DEFAULT '{}',
    entity_refs_json     TEXT NOT NULL DEFAULT '[]',
    source_refs_json     TEXT NOT NULL DEFAULT '{}',
    llm_result_refs_json TEXT NOT NULL DEFAULT '{}',
    weight               REAL NOT NULL DEFAULT 1.0,
    created_at           TEXT NOT NULL,
    metadata_json        TEXT NOT NULL DEFAULT '{}',
    UNIQUE (raw_document_id, unit_key)
);

CREATE INDEX IF NOT EXISTS idx_asset_retrieval_units_document
    ON asset_retrieval_units(raw_document_id);

CREATE INDEX IF NOT EXISTS idx_asset_retrieval_units_target
    ON asset_retrieval_units(target_type, target_id);

CREATE INDEX IF NOT EXISTS idx_asset_retrieval_units_unit_type
    ON asset_retrieval_units(unit_type);

CREATE INDEX IF NOT EXISTS idx_asset_retrieval_units_block_role
    ON asset_retrieval_units(block_type, semantic_role);

CREATE VIRTUAL TABLE IF NOT EXISTS asset_retrieval_units_fts
USING fts5(
    retrieval_unit_id UNINDEXED,
    title,
    text,
    search_text,
    tokenize = 'unicode61'
);

CREATE TRIGGER IF NOT EXISTS trg_asset_retrieval_units_ai
AFTER INSERT ON asset_retrieval_units
BEGIN
    INSERT INTO asset_retrieval_units_fts (retrieval_unit_id, title, text, search_text)
    VALUES (new.id, coalesce(new.title, ''), new.text, new.search_text);
END;

CREATE TRIGGER IF NOT EXISTS trg_asset_retrieval_units_au
AFTER UPDATE ON asset_retrieval_units
BEGIN
    DELETE FROM asset_retrieval_units_fts WHERE retrieval_unit_id = old.id;
    INSERT INTO asset_retrieval_units_fts (retrieval_unit_id, title, text, search_text)
    VALUES (new.id, coalesce(new.title, ''), new.text, new.search_text);
END;

CREATE TRIGGER IF NOT EXISTS trg_asset_retrieval_units_ad
AFTER DELETE ON asset_retrieval_units
BEGIN
    DELETE FROM asset_retrieval_units_fts WHERE retrieval_unit_id = old.id;
END;

CREATE TABLE IF NOT EXISTS asset_retrieval_embeddings (
    id                 TEXT PRIMARY KEY,
    retrieval_unit_id  TEXT NOT NULL REFERENCES asset_retrieval_units(id) ON DELETE CASCADE,
    embedding_model    TEXT NOT NULL,
    embedding_provider TEXT NOT NULL,
    text_kind          TEXT NOT NULL,
    embedding_dim      INTEGER NOT NULL CHECK (embedding_dim > 0),
    embedding_vector   TEXT NOT NULL,
    content_hash       TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    metadata_json      TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_asset_retrieval_embeddings_unit
    ON asset_retrieval_embeddings(retrieval_unit_id);

CREATE INDEX IF NOT EXISTS idx_asset_retrieval_embeddings_model
    ON asset_retrieval_embeddings(embedding_provider, embedding_model);

-- Legacy compatibility tables. They are retained for migration/inspection only
-- and are not part of the v1.1 primary retrieval path.
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
    has_variants       INTEGER NOT NULL DEFAULT 0 CHECK (has_variants IN (0, 1)),
    variant_policy     TEXT NOT NULL DEFAULT 'none',
    quality_score      REAL,
    created_at         TEXT NOT NULL,
    metadata_json      TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS asset_canonical_segment_sources (
    id                   TEXT PRIMARY KEY,
    canonical_segment_id TEXT NOT NULL REFERENCES asset_canonical_segments(id) ON DELETE CASCADE,
    raw_segment_id       TEXT NOT NULL REFERENCES asset_raw_segments(id) ON DELETE CASCADE,
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
    similarity_score     REAL,
    diff_summary         TEXT,
    metadata_json        TEXT NOT NULL DEFAULT '{}',
    UNIQUE (canonical_segment_id, raw_segment_id)
);

CREATE INDEX IF NOT EXISTS idx_asset_canonical_segment_sources_canonical
    ON asset_canonical_segment_sources(canonical_segment_id);

CREATE INDEX IF NOT EXISTS idx_asset_canonical_segment_sources_raw
    ON asset_canonical_segment_sources(raw_segment_id);
