-- CoreMasterKB M1 Asset Core Schema v0.5
--
-- Purpose:
--   Shared database contract between Knowledge Mining and Agent Serving.
--   Mining writes complete staging publish versions. Serving reads only the
--   single active publish version. M1 uses physical snapshots: every publish
--   version is a complete serviceable knowledge asset snapshot.
--
-- Scope:
--   This schema intentionally does not define ontology, facts, embeddings, or
--   external metadata manifests. M1 input is a normal corpus folder. Mining
--   discovers source artifacts recursively, registers all supported documents,
--   parses only Markdown/TXT into raw segments, canonicalizes those segments,
--   and publishes an active version.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS asset;

CREATE TABLE IF NOT EXISTS asset.source_batches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_code      TEXT NOT NULL UNIQUE,
    source_type     TEXT NOT NULL,
    description     TEXT,
    created_by      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json   JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT ck_source_batches_source_type
        CHECK (
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
    CONSTRAINT ck_source_batches_metadata_object
        CHECK (jsonb_typeof(metadata_json) = 'object')
);

CREATE TABLE IF NOT EXISTS asset.publish_versions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_code            TEXT NOT NULL UNIQUE,
    status                  TEXT NOT NULL,
    base_publish_version_id UUID REFERENCES asset.publish_versions(id) ON DELETE SET NULL,
    source_batch_id         UUID REFERENCES asset.source_batches(id) ON DELETE SET NULL,
    description             TEXT,
    build_started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    build_finished_at       TIMESTAMPTZ,
    activated_at            TIMESTAMPTZ,
    build_error             TEXT,
    metadata_json           JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT ck_publish_versions_status
        CHECK (status IN ('staging', 'active', 'archived', 'failed')),
    CONSTRAINT ck_publish_versions_metadata_object
        CHECK (jsonb_typeof(metadata_json) = 'object')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_publish_versions_one_active
    ON asset.publish_versions ((true))
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_publish_versions_status
    ON asset.publish_versions(status);

CREATE INDEX IF NOT EXISTS idx_publish_versions_base
    ON asset.publish_versions(base_publish_version_id);

CREATE INDEX IF NOT EXISTS idx_publish_versions_source_batch
    ON asset.publish_versions(source_batch_id);

CREATE TABLE IF NOT EXISTS asset.raw_documents (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    publish_version_id      UUID NOT NULL REFERENCES asset.publish_versions(id) ON DELETE CASCADE,
    document_key            TEXT NOT NULL,
    source_uri              TEXT NOT NULL,
    relative_path           TEXT NOT NULL,
    file_name               TEXT NOT NULL,
    file_type               TEXT NOT NULL,
    source_type             TEXT,
    title                   TEXT,
    document_type           TEXT,
    content_hash            TEXT NOT NULL,
    copied_from_document_id UUID REFERENCES asset.raw_documents(id) ON DELETE SET NULL,
    origin_batch_id         UUID REFERENCES asset.source_batches(id) ON DELETE SET NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scope_json              JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags_json               JSONB NOT NULL DEFAULT '[]'::jsonb,
    structure_quality       TEXT NOT NULL DEFAULT 'unknown',
    processing_profile_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json           JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT ck_raw_documents_file_type
        CHECK (file_type IN ('markdown', 'html', 'pdf', 'doc', 'docx', 'txt', 'other')),
    CONSTRAINT ck_raw_documents_source_type
        CHECK (
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
    CONSTRAINT ck_raw_documents_document_type
        CHECK (
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
    CONSTRAINT ck_raw_documents_scope_object
        CHECK (jsonb_typeof(scope_json) = 'object'),
    CONSTRAINT ck_raw_documents_tags_array
        CHECK (jsonb_typeof(tags_json) = 'array'),
    CONSTRAINT ck_raw_documents_processing_profile_object
        CHECK (jsonb_typeof(processing_profile_json) = 'object'),
    CONSTRAINT ck_raw_documents_metadata_object
        CHECK (jsonb_typeof(metadata_json) = 'object'),
    CONSTRAINT ck_raw_documents_structure_quality
        CHECK (
            structure_quality IN (
                'markdown_native',
                'plain_text_only',
                'full_html',
                'mixed',
                'unknown'
            )
        ),
    CONSTRAINT uq_raw_documents_version_key
        UNIQUE (publish_version_id, document_key),
    CONSTRAINT uq_raw_documents_id_version
        UNIQUE (id, publish_version_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_documents_publish_version
    ON asset.raw_documents(publish_version_id);

CREATE INDEX IF NOT EXISTS idx_raw_documents_origin_batch
    ON asset.raw_documents(origin_batch_id);

CREATE INDEX IF NOT EXISTS idx_raw_documents_content_hash
    ON asset.raw_documents(publish_version_id, content_hash);

CREATE INDEX IF NOT EXISTS idx_raw_documents_source_type
    ON asset.raw_documents(publish_version_id, source_type);

CREATE INDEX IF NOT EXISTS idx_raw_documents_file_type
    ON asset.raw_documents(publish_version_id, file_type);

CREATE INDEX IF NOT EXISTS idx_raw_documents_document_type
    ON asset.raw_documents(publish_version_id, document_type);

CREATE INDEX IF NOT EXISTS idx_raw_documents_relative_path
    ON asset.raw_documents(publish_version_id, relative_path);

CREATE INDEX IF NOT EXISTS idx_raw_documents_scope_json
    ON asset.raw_documents
    USING GIN (scope_json);

CREATE INDEX IF NOT EXISTS idx_raw_documents_tags_json
    ON asset.raw_documents
    USING GIN (tags_json);

CREATE TABLE IF NOT EXISTS asset.raw_segments (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    publish_version_id     UUID NOT NULL REFERENCES asset.publish_versions(id) ON DELETE CASCADE,
    raw_document_id        UUID NOT NULL,
    segment_key            TEXT NOT NULL,
    segment_index          INTEGER NOT NULL,
    section_path           JSONB NOT NULL DEFAULT '[]'::jsonb,
    section_title          TEXT,
    block_type             TEXT NOT NULL DEFAULT 'unknown',
    semantic_role          TEXT NOT NULL DEFAULT 'unknown',
    raw_text               TEXT NOT NULL,
    normalized_text        TEXT NOT NULL,
    content_hash           TEXT NOT NULL,
    normalized_hash        TEXT NOT NULL,
    token_count            INTEGER,
    copied_from_segment_id UUID REFERENCES asset.raw_segments(id) ON DELETE SET NULL,
    structure_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_offsets_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    entity_refs_json       JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata_json          JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT fk_raw_segments_document_same_version
        FOREIGN KEY (raw_document_id, publish_version_id)
        REFERENCES asset.raw_documents(id, publish_version_id)
        ON DELETE CASCADE,
    CONSTRAINT ck_raw_segments_segment_index
        CHECK (segment_index >= 0),
    CONSTRAINT ck_raw_segments_token_count
        CHECK (token_count IS NULL OR token_count >= 0),
    CONSTRAINT ck_raw_segments_section_path_array
        CHECK (jsonb_typeof(section_path) = 'array'),
    CONSTRAINT ck_raw_segments_block_type
        CHECK (block_type IN ('paragraph', 'table', 'list', 'code', 'blockquote', 'html_table', 'raw_html', 'unknown')),
    CONSTRAINT ck_raw_segments_semantic_role
        CHECK (semantic_role IN ('concept', 'parameter', 'example', 'note', 'procedure_step', 'troubleshooting_step', 'constraint', 'alarm', 'checklist', 'unknown')),
    CONSTRAINT ck_raw_segments_structure_object
        CHECK (jsonb_typeof(structure_json) = 'object'),
    CONSTRAINT ck_raw_segments_source_offsets_object
        CHECK (jsonb_typeof(source_offsets_json) = 'object'),
    CONSTRAINT ck_raw_segments_entity_refs_array
        CHECK (jsonb_typeof(entity_refs_json) = 'array'),
    CONSTRAINT ck_raw_segments_metadata_object
        CHECK (jsonb_typeof(metadata_json) = 'object'),
    CONSTRAINT uq_raw_segments_version_document_key
        UNIQUE (publish_version_id, raw_document_id, segment_key),
    CONSTRAINT uq_raw_segments_id_version
        UNIQUE (id, publish_version_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_segments_publish_document
    ON asset.raw_segments(publish_version_id, raw_document_id);

CREATE INDEX IF NOT EXISTS idx_raw_segments_normalized_hash
    ON asset.raw_segments(publish_version_id, normalized_hash);

CREATE INDEX IF NOT EXISTS idx_raw_segments_block_role
    ON asset.raw_segments(publish_version_id, block_type, semantic_role);

CREATE INDEX IF NOT EXISTS idx_raw_segments_entity_refs_json
    ON asset.raw_segments
    USING GIN (entity_refs_json);

CREATE TABLE IF NOT EXISTS asset.canonical_segments (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    publish_version_id UUID NOT NULL REFERENCES asset.publish_versions(id) ON DELETE CASCADE,
    canonical_key      TEXT NOT NULL,
    block_type         TEXT NOT NULL DEFAULT 'unknown',
    semantic_role      TEXT NOT NULL DEFAULT 'unknown',
    title              TEXT,
    canonical_text     TEXT NOT NULL,
    summary            TEXT,
    search_text        TEXT NOT NULL,
    entity_refs_json   JSONB NOT NULL DEFAULT '[]'::jsonb,
    scope_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    has_variants       BOOLEAN NOT NULL DEFAULT FALSE,
    variant_policy     TEXT NOT NULL DEFAULT 'none',
    quality_score      NUMERIC(5,4),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json      JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT ck_canonical_segments_block_type
        CHECK (block_type IN ('paragraph', 'table', 'list', 'code', 'blockquote', 'html_table', 'raw_html', 'unknown')),
    CONSTRAINT ck_canonical_segments_semantic_role
        CHECK (semantic_role IN ('concept', 'parameter', 'example', 'note', 'procedure_step', 'troubleshooting_step', 'constraint', 'alarm', 'checklist', 'unknown')),
    CONSTRAINT ck_canonical_segments_entity_refs_array
        CHECK (jsonb_typeof(entity_refs_json) = 'array'),
    CONSTRAINT ck_canonical_segments_scope_object
        CHECK (jsonb_typeof(scope_json) = 'object'),
    CONSTRAINT ck_canonical_segments_variant_policy
        CHECK (variant_policy IN ('none', 'prefer_latest', 'require_scope', 'require_disambiguation', 'manual_review')),
    CONSTRAINT ck_canonical_segments_quality_score
        CHECK (quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)),
    CONSTRAINT ck_canonical_segments_metadata_object
        CHECK (jsonb_typeof(metadata_json) = 'object'),
    CONSTRAINT uq_canonical_segments_version_key
        UNIQUE (publish_version_id, canonical_key),
    CONSTRAINT uq_canonical_segments_id_version
        UNIQUE (id, publish_version_id)
);

CREATE INDEX IF NOT EXISTS idx_canonical_segments_block_role
    ON asset.canonical_segments(publish_version_id, block_type, semantic_role);

CREATE INDEX IF NOT EXISTS idx_canonical_segments_variants
    ON asset.canonical_segments(publish_version_id, has_variants, variant_policy);

CREATE INDEX IF NOT EXISTS idx_canonical_segments_scope_json
    ON asset.canonical_segments
    USING GIN (scope_json);

CREATE INDEX IF NOT EXISTS idx_canonical_segments_entity_refs_json
    ON asset.canonical_segments
    USING GIN (entity_refs_json);

CREATE INDEX IF NOT EXISTS idx_canonical_segments_search_text_fts
    ON asset.canonical_segments
    USING GIN (to_tsvector('simple', search_text));

CREATE TABLE IF NOT EXISTS asset.canonical_segment_sources (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    publish_version_id   UUID NOT NULL REFERENCES asset.publish_versions(id) ON DELETE CASCADE,
    canonical_segment_id UUID NOT NULL,
    raw_segment_id       UUID NOT NULL,
    relation_type        TEXT NOT NULL,
    is_primary           BOOLEAN NOT NULL DEFAULT FALSE,
    priority             INTEGER NOT NULL DEFAULT 100,
    similarity_score     NUMERIC(5,4),
    diff_summary         TEXT,
    metadata_json        JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT fk_sources_canonical_same_version
        FOREIGN KEY (canonical_segment_id, publish_version_id)
        REFERENCES asset.canonical_segments(id, publish_version_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_sources_raw_same_version
        FOREIGN KEY (raw_segment_id, publish_version_id)
        REFERENCES asset.raw_segments(id, publish_version_id)
        ON DELETE CASCADE,
    CONSTRAINT ck_sources_relation_type
        CHECK (
            relation_type IN (
                'primary',
                'exact_duplicate',
                'normalized_duplicate',
                'near_duplicate',
                'scope_variant',
                'conflict_candidate'
            )
        ),
    CONSTRAINT ck_sources_priority
        CHECK (priority >= 0),
    CONSTRAINT ck_sources_similarity_score
        CHECK (similarity_score IS NULL OR (similarity_score >= 0 AND similarity_score <= 1)),
    CONSTRAINT ck_sources_metadata_object
        CHECK (jsonb_typeof(metadata_json) = 'object'),
    CONSTRAINT uq_sources_canonical_raw
        UNIQUE (canonical_segment_id, raw_segment_id)
);

CREATE INDEX IF NOT EXISTS idx_sources_canonical
    ON asset.canonical_segment_sources(publish_version_id, canonical_segment_id);

CREATE INDEX IF NOT EXISTS idx_sources_raw
    ON asset.canonical_segment_sources(publish_version_id, raw_segment_id);

CREATE INDEX IF NOT EXISTS idx_sources_primary_priority
    ON asset.canonical_segment_sources(canonical_segment_id, is_primary, priority);

CREATE INDEX IF NOT EXISTS idx_sources_relation_type
    ON asset.canonical_segment_sources(publish_version_id, relation_type);
