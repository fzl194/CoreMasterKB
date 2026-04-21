# v1.1 Knowledge Mining — Claude Mining Handoff

- **Task**: TASK-20260421-v11-knowledge-mining
- **Date**: 2026-04-21
- **From**: Claude Mining
- **To**: Codex (审查)
> 状态：已审查

## 任务目标

将 `knowledge_mining` 从旧 M1 主链（raw_documents / canonical / publish_versions）重构到 v1.1 正式主链：

```
source_batch → document → shared snapshot → document_snapshot_link → raw_segments / raw_segment_relations / retrieval_units → build → release
```

## 本次实现范围

### 完整两阶段 Pipeline

**Phase 1 — Document Mining（文档级，每文档独立执行）：**
ingest → parse → segment → enrich → build_relations → build_retrieval_units → select_snapshot

**Phase 2 — Build & Publish（全局操作）：**
assemble_build → validate_build → publish_release

### 全量模块清单（6 次提交）

| 批次 | 模块 | 说明 |
|------|------|------|
| T0 | old/ | 旧代码移到 old/knowledge_mining_m1/ |
| T1-T3 | models.py, db.py, hash_utils.py | 12 frozen dataclass + 双库适配器 + 保守 hash |
| T4-T7 | text_utils, parsers, structure, segmentation, extractors, runtime | 移植 + 重写 |
| T8-T13 | enrich, relations, retrieval_units, snapshot, publishing, jobs/run.py | 增量模块 |
| T14-T15 | test_v11_pipeline.py, README.md | 30 测试 + 文档 |
| fix | db.py, ingestion, runtime, jobs/run.py | 自查修复 |

### 自查修复（3 CRITICAL + 3 HIGH）

1. **CRITICAL**: `upsert_document` ON CONFLICT 后读回实际 row id
2. **CRITICAL**: `upsert_snapshot` ON CONFLICT 后读回实际 row id
3. **CRITICAL**: 非可解析文件（PDF/DOCX 等）使用 raw_hash 作为 normalized_content_hash fallback，避免空内容碰撞
4. **HIGH**: `update_run_status` 将 build_id 从 **counters 中分离为显式参数
5. **HIGH**: `RuntimeTracker.complete_run` 接受 build_id keyword
6. **HIGH**: `jobs/run.py` 通过 keyword 传递 build_id

## 明确不在本次范围内的内容

- HTML/PDF/DOC/DOCX 正文解析（只登记，不解析）
- 断点续跑自动恢复入口（RuntimeTracker 已产出 resume plan，但 jobs/run.py 未实现自动恢复）
- LLM 增强（v1.2 范围）
- 向量嵌入（v1.2 范围）
- 语义关系（v1.2 范围）

## 改动文件清单

### 新增文件
- `knowledge_mining/mining/models.py` — 12 frozen dataclass + 11 frozenset
- `knowledge_mining/mining/db.py` — AssetCoreDB + MiningRuntimeDB 双库适配器
- `knowledge_mining/mining/hash_utils.py` — 保守归一化 + SHA256
- `knowledge_mining/mining/text_utils.py` — CJK-aware tokenization
- `knowledge_mining/mining/parsers/__init__.py` — MarkdownParser / PlainTextParser / PassthroughParser
- `knowledge_mining/mining/structure/__init__.py` — markdown-it → SectionNode 树
- `knowledge_mining/mining/segmentation/__init__.py` — SectionNode → RawSegmentData
- `knowledge_mining/mining/extractors.py` — RuleBasedEntityExtractor + DefaultRoleClassifier
- `knowledge_mining/mining/enrich/__init__.py` — 规则增强
- `knowledge_mining/mining/relations/__init__.py` — 结构关系
- `knowledge_mining/mining/retrieval_units/__init__.py` — raw_text + contextual_text + entity_card
- `knowledge_mining/mining/snapshot/__init__.py` — 共享快照
- `knowledge_mining/mining/publishing/__init__.py` — build + release
- `knowledge_mining/mining/runtime/__init__.py` — RuntimeTracker
- `knowledge_mining/mining/jobs/run.py` — Pipeline 编排器
- `knowledge_mining/mining/ingestion/__init__.py` — 递归扫描
- `knowledge_mining/tests/test_v11_pipeline.py` — 30 测试

### 修改文件
- `knowledge_mining/README.md` — v1.1 重写

### 移除文件
- 旧代码移到 `old/knowledge_mining_m1/`

## 关键设计决策

1. **共享快照三层模型**: document (document_key) → snapshot (normalized_content_hash) → link，保守归一化策略
2. **Heading 独立成段**: heading 作为 block_type='heading' 独立 raw_segment，支撑 section_header_of 关系
3. **Build merge 语义**: 当前 build_mode 固定 "full"；incremental 框架已预留但未启用
4. **Relations 两层预留**: v1.1 只写结构关系（previous/next、same_section、section_header_of），同一张表 v1.2 加语义关系
5. **双库隔离**: asset_core.sqlite 存内容资产，mining_runtime.sqlite 存过程态
6. **阶段事件**: 9 个 stage 完整覆盖，支持 nullable run_document_id
7. **publish() 独立入口**: 与 run() 分离，支持延迟发布

## 已执行验证

```
30 tests passed:
- TestModels (2): dataclass frozen + 常量与 schema 对齐
- TestAssetCoreDB (5): batch CRUD, document upsert, snapshot sharing, build, release chain
- TestMiningRuntimeDB (3): run lifecycle, stage events, resume plan
- TestHashUtils (3): normalization, deterministic, raw vs normalized
- TestIngestion (2): discover files, skip unrecognized
- TestStructure (2): heading tree, table structure
- TestSegmentation (2): heading segments, segment hashes
- TestExtractors (2): command extraction, role classifier
- TestEnrich (1): enrich adds metadata
- TestRelations (2): build relations, section_header_of only from heading
- TestRetrievalUnits (1): build units
- TestSnapshot (1): select or create
- TestPublishing (1): assemble and publish
- TestEndToEndPipeline (3): full pipeline, phase1_only, publish_after_phase1

端到端验证: 3 docs → 17 segments → 8 headings → 89 relations → 34 retrieval units → active release
```

## 未验证项

- 断点续跑端到端验证（RuntimeTracker 产出 resume plan 已测试，但完整恢复流程未实现）
- 并发写入场景（单进程单线程模型，SQLite WAL 未测试）
- 超大文档处理（>10MB markdown 未测试）

## 已知风险

1. `asset_db.commit()` 在文档处理成功后才提交，但如果 segment/relation/retrieval_unit 写入一半失败，会有部分数据残留（当前无清理机制）
2. `publishing/assemble_build` 中 incremental 模式框架已写但未启用，build_mode 固定 "full"
3. `structure/__init__.py` 依赖 markdown-it，未做降级处理

## 指定给 Codex 的审查重点

1. **UPSERT id 正确性**: 确认 db.py 中 upsert_document / upsert_snapshot 的 readback 逻辑是否可靠
2. **shared snapshot 模型**: 确认三层模型（document → snapshot → link）是否符合 v1.1 SQL schema 契约
3. **build/release 链路**: 确认 assemble_build 的 merge 语义和 publish_release 的 activate/deactivate 是否正确
4. **mining_runtime 阶段事件**: 确认 9 个 stage 覆盖是否完整
5. **pipeline 编排**: 确认 jobs/run.py 的异常处理和 commit 时机是否合理
6. **build_id 传递链**: 确认从 assemble_build → tracker.complete_run → mining_runs.build_id 的完整传递

## 管理员本轮直接介入记录

- 管理员要求自查后再移交，已执行自查并修复 3C+3H 问题
