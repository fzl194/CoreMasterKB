# M1 Asset Core Schema

> 当前版本：v0.5
> PostgreSQL SQL 定义：`knowledge_assets/schemas/001_asset_core.sql`
> SQLite dev SQL 定义：`knowledge_assets/schemas/001_asset_core.sqlite.sql`
> 适用任务：`TASK-20260415-m1-knowledge-mining`、`TASK-20260415-m1-agent-serving`

## 目标

`knowledge_assets/schemas/` 是 Knowledge Mining 和 Agent Serving 的唯一数据库契约来源。

M1 阶段采用物理快照模型：每个 `publish_version` 都是一份完整可服务知识资产快照。Mining 写入 `staging` 版本，校验通过后原子切换为 `active`；Serving 只读唯一 `active` 版本。

M1 的输入基线是一个普通语料文件夹。Mining 递归发现 source artifacts，不依赖 `manifest.jsonl`、`html_to_md_mapping.json/csv` 或其他外部元数据文件。Markdown 和 TXT 在 M1 生成 `raw_segments`；HTML/PDF/DOC/DOCX 等先登记为 `raw_documents`，不生成切片。

本 schema 不定义 ontology、fact、embedding 或旧项目 evidence。L2 表命名为 `canonical_segment_sources`，表示 L1 归并段到 L0 原始段的来源映射、重复关系、scope 变体和冲突候选。

## 表总览

| 表 | 层级 | 作用 | Mining | Serving |
|---|---:|---|---|---|
| `asset.source_batches` | 输入批次 | 记录一次文件夹扫描/上传任务及批次默认参数 | 写入 | 审计可读 |
| `asset.publish_versions` | 发布控制 | 记录一次完整资产快照，`active` 是 Serving 入口 | 写入 / 激活 | 读取 active |
| `asset.raw_documents` | L0 文档 | 发布版本内每个源文件的文档级登记 | 写入 | 来源展示可读 |
| `asset.raw_segments` | L0 切片 | Markdown/TXT 解析后的原始知识切片 | 写入 | 下钻读取 |
| `asset.canonical_segments` | L1 归并段 | 去重归并后的主检索对象 | 写入 | 主检索 |
| `asset.canonical_segment_sources` | L2 映射 | L1 到 L0 的来源、重复、变体和冲突关系 | 写入 | 下钻选择 |

SQLite dev mode 使用同语义前缀表名：

| PostgreSQL 表 | SQLite dev 表 |
|---|---|
| `asset.source_batches` | `asset_source_batches` |
| `asset.publish_versions` | `asset_publish_versions` |
| `asset.raw_documents` | `asset_raw_documents` |
| `asset.raw_segments` | `asset_raw_segments` |
| `asset.canonical_segments` | `asset_canonical_segments` |
| `asset.canonical_segment_sources` | `asset_canonical_segment_sources` |

## 版本模型

`source_batch` 和 `publish_version` 是两个不同概念。

| 概念 | 含义 |
|---|---|
| `source_batch` | 本次输入文件夹、上传批次或扫描任务，以及批次级默认上下文 |
| `publish_version` | 本次发布后 Serving 可读取的完整知识库快照 |

M1 发布规则：

| 步骤 | 动作 |
|---|---|
| 1 | 读取当前唯一 `active` 版本，第一次发布时为空 |
| 2 | 创建新的 `source_batch` 和 `staging` publish version |
| 3 | 递归扫描输入文件夹，登记所有支持识别的 source artifacts 到 `raw_documents` |
| 4 | 只对 Markdown/TXT 生成 `raw_segments` |
| 5 | 基于新版本完整 L0 全量重建 L1 `canonical_segments` |
| 6 | 基于新版本 L1/L0 全量重建 L2 `canonical_segment_sources` |
| 7 | 校验 L0/L1/L2 完整性 |
| 8 | 事务切换旧 `active` 为 `archived`，新 `staging` 为 `active` |
| 9 | 构建失败时标记新版本 `failed`，旧 `active` 保持不变 |

M1 可先全量物理快照，不要求本轮实现未变化文档复制；`copied_from_document_id` 和 `copied_from_segment_id` 为后续增量复制预留。

## source_batches

`source_batches.metadata_json` 记录批次级默认参数。用户在前端填写的“这一批属于命令”“这一批属于某个网元/项目”等信息写在这里，再由 Mining 合并到文档画像。

示例：

```json
{
  "ingest_mode": "folder_scan",
  "storage_root_uri": "storage://uploads/batch_20260417_001",
  "original_root_name": "核心网命令资料",
  "default_document_type": "command",
  "default_source_type": "manual_upload",
  "batch_scope": {
    "product": "CloudCore",
    "product_version": "V100R023",
    "network_elements": ["SMF", "UPF"],
    "project": "项目A"
  },
  "tags": ["command", "core_network"]
}
```

## raw_documents

`raw_documents` 记录每个源文件，不只记录已解析文件。M1 必须识别并登记：

```text
.md / .markdown / .txt / .html / .htm / .pdf / .doc / .docx
```

| 字段 | 说明 |
|---|---|
| `document_key` | 稳定文档身份；M1 使用规范化 `relative_path` |
| `source_uri` | 后端实际读取位置 |
| `relative_path` | 相对本批次输入根目录路径 |
| `file_name` | 文件名 |
| `file_type` | `markdown/html/pdf/doc/docx/txt/other` |
| `source_type` | 来源方式，如 `manual_upload/folder_scan/official_vendor/expert_authored` |
| `title` | 文档标题，可由 H1、文件名或内容推断 |
| `document_type` | 内容类型，如 `command/feature/procedure/troubleshooting/expert_note/reference` |
| `content_hash` | 文件内容 hash，不是路径 hash |
| `scope_json` | 产品、版本、网元、项目、场景、作者等通用上下文 |
| `tags_json` | 标签 |
| `structure_quality` | `markdown_native/plain_text_only/full_html/mixed/unknown` |
| `processing_profile_json` | parser、normalization、extraction quality 等处理过程 |
| `metadata_json` | `parse_status/skip_reason/inferred_by` 等扩展 |

产品、版本、网元不再作为外层字段，统一进入 `scope_json`：

```json
{
  "product": "CloudCore",
  "product_version": "V100R023",
  "network_elements": ["SMF", "UPF"],
  "project": "项目A",
  "scenario": "N4 interface"
}
```

`source_uri` 和 `relative_path` 的区别：

| 字段 | 含义 | 稳定性 |
|---|---|---:|
| `source_uri` | 后端实际读取位置，如上传存储 URI 或扫描路径 | 不稳定 |
| `relative_path` | 相对本批次根目录路径 | 相对稳定 |

## raw_segments

`raw_segments` 是 Markdown/TXT 解析后的原始知识切片。HTML/PDF/DOC/DOCX 在 M1 只登记 `raw_documents`，不生成 `raw_segments`。

| 字段 | 说明 |
|---|---|
| `segment_key` | 文档内稳定切片 key |
| `segment_index` | 文档内顺序 |
| `section_path` | 结构化章节路径，建议元素包含 `title` 和 `level` |
| `section_title` | 当前章节标题 |
| `block_type` | 结构类型 |
| `semantic_role` | 语义角色 |
| `raw_text` | 原文 |
| `normalized_text` | 规范化文本 |
| `content_hash` | 原文 hash |
| `normalized_hash` | 规范化文本 hash |
| `structure_json` | 表格、列表、代码等结构元数据 |
| `source_offsets_json` | parser、block index、行号等来源位置 |
| `entity_refs_json` | 命令、网元、术语、特性等实体引用 |
| `metadata_json` | 其他扩展 |

`block_type`：

```text
paragraph / table / list / code / blockquote / html_table / raw_html / unknown
```

`semantic_role`：

```text
concept / parameter / example / note / procedure_step / troubleshooting_step / constraint / alarm / checklist / unknown
```

`entity_refs_json` 示例：

```json
[
  {"type": "command", "name": "ADD APN"},
  {"type": "network_element", "name": "SMF"},
  {"type": "term", "name": "DNN"}
]
```

`structure_json` 最低约定：

| `block_type` | `structure_json` 建议 |
|---|---|
| `paragraph` | `{"paragraph_count": 2}` |
| `list` | `{"ordered": true, "items": ["步骤1", "步骤2"]}` |
| `table` | `{"columns": [...], "rows": [...], "row_count": 2, "col_count": 2}` |
| `code` | `{"language": "mml"}` |
| `html_table` | `{"raw_html_preserved": true, "row_count": 3, "col_count": 2}` |

## canonical_segments

`canonical_segments` 是 Serving 主检索对象。它不是简单复制某个 raw segment，而是多个 raw segments 的服务视角归并结果。

| 字段 | 说明 |
|---|---|
| `canonical_key` | 稳定 canonical key |
| `block_type` | 主结构类型 |
| `semantic_role` | 语义角色 |
| `title` | 标题 |
| `canonical_text` | 标准正文 |
| `summary` | 摘要 |
| `search_text` | 检索文本 |
| `entity_refs_json` | 多个 raw 来源实体的去重合集 |
| `scope_json` | 多个 raw 来源文档 scope 的合并结果 |
| `has_variants` | 是否存在需要区分的变体 |
| `variant_policy` | 变体选择策略 |
| `quality_score` | 质量分 |
| `metadata_json` | canonicalization 方法、主来源、scope 合并策略等 |

`variant_policy`：

```text
none / prefer_latest / require_scope / require_disambiguation / manual_review
```

canonical JSON 聚合规则：

| 字段 | 聚合规则 |
|---|---|
| `entity_refs_json` | 对所有来源 raw segment 的 `entity_refs_json` 按 `type + normalized_name` 去重，可记录 `source_count` |
| `scope_json` | 对所有来源 raw document 的 `scope_json` 合并；数组去重 union，冲突写入 `metadata_json.scope_merge.conflicts` |
| `metadata_json` | 记录 `canonicalization.method/source_count/primary_raw_segment_id/scope_merge` 等归并信息 |

结构细节保留在 `raw_segments.structure_json`。canonical 层只保留 `block_type` 和必要的结构摘要，不复制所有 raw 结构。

## canonical_segment_sources

`canonical_segment_sources` 记录 canonical 与 raw segment 的来源关系。

`relation_type`：

```text
primary / exact_duplicate / normalized_duplicate / near_duplicate / scope_variant / conflict_candidate
```

| 字段 | 说明 |
|---|---|
| `canonical_segment_id` | 指向 L1 |
| `raw_segment_id` | 指向 L0 |
| `relation_type` | 来源关系 |
| `is_primary` | 是否主来源；每个 canonical 必须有且只有一个 primary |
| `priority` | 来源优先级；primary 应为最高优先级 |
| `similarity_score` | 相似度 |
| `diff_summary` | 差异摘要 |
| `metadata_json` | 变体维度、scope 差异、算法信息 |

scope 差异示例：

```json
{
  "variant_dimensions": ["product_version", "network_elements"],
  "primary_scope": {
    "product_version": "V1",
    "network_elements": ["SMF"]
  },
  "source_scope": {
    "product_version": "V2",
    "network_elements": ["UPF"]
  }
}
```

## Serving 读取规则

Serving 不读取多个版本拼接结果，也不读取 `staging` 或 `failed`。

每次请求先确定唯一 active version：

```sql
SELECT id
FROM asset.publish_versions
WHERE status = 'active';
```

之后所有资产查询都必须带：

```text
publish_version_id = :active_publish_version_id
```

主路径：

```text
active publish_version
  -> asset.canonical_segments
  -> asset.canonical_segment_sources
  -> asset.raw_segments
  -> asset.raw_documents
```

Serving 不读取文件系统，不依赖 `source_uri` 打开原文件；Serving 只读 DB 中已经发布的 `canonical_text/raw_text/structure_json/source_offsets_json/relative_path`。

## M1 边界

M1 必须做：

| 项 | 要求 |
|---|---|
| 输入 | 普通文件夹递归扫描 |
| 文件登记 | 所有识别文件登记 `raw_documents` |
| 解析 | 只对 Markdown/TXT 生成 `raw_segments` |
| 归并 | exact / normalized / scope variant 基础归并 |
| 发布 | staging -> active，failed 不影响旧 active |
| 契约 | Mining 生成 DB，Serving 读取 active canonical 并下钻来源 |

M1 明确不做：

| 不做 |
|---|
| HTML/PDF/DOCX 深度解析 |
| embedding |
| LLM 抽取事实 |
| ontology / graph |
| 命令参数强结构化抽取 |
| 增量复制 |
| 前端上传实现 |
| 外部元数据文件适配 |

## 关键约束

| 约束 | 目的 |
|---|---|
| 全局最多一个 `active` publish version | Serving 始终有唯一读取入口 |
| `raw_documents(publish_version_id, document_key)` 唯一 | 同一版本内文档身份唯一 |
| `raw_segments(publish_version_id, raw_document_id, segment_key)` 唯一 | 同一文档内切片身份唯一 |
| `canonical_segments(publish_version_id, canonical_key)` 唯一 | 同一版本内 L1 归并对象唯一 |
| L2 复合外键带 `publish_version_id` | 防止 L1/L0 跨版本映射 |

## 测试要求

管理员会安排专人准备普通混合测试文件夹，不包含 `manifest.jsonl`、`html_to_md_mapping.json/csv` 或其他外部元数据文件。

Claude Mining 必须基于该测试文件夹验收：

| 场景 | 期望 |
|---|---|
| md/txt/html/pdf/docx 混合目录 | 全部登记 `raw_documents` |
| MD/TXT | 生成 `raw_segments` |
| HTML/PDF/DOCX | 只登记，不切片 |
| 连续发布两次 | 旧 active archived，新 active 唯一 |
| 失败发布 | 新版本 failed，旧 active 不变 |
| Mining -> SQLite -> Serving | Serving 能读取 canonical 并下钻 raw/document |

任何 schema 变更都必须同步更新 PostgreSQL DDL、SQLite DDL、本 README、架构文档，并在 Mining 与 Serving 两个任务消息文件中说明兼容性影响。
