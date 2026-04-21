# Asset Core Schema

> 当前版本：v1.1  
> SQLite 契约：`knowledge_assets/schemas/001_asset_core.sqlite.sql`  
> Generic SQL 基线：`knowledge_assets/schemas/001_asset_core.sql`

## 目标

`knowledge_assets/schemas/` 是 CoreMasterKB 当前共享的知识资产数据库契约来源。

这版 schema 对应我们最新定下的 1.1 原则：

1. Asset 表只存当前 active 资产，不做历史全量快照。
2. `asset_publish_versions` 只保留最小发布控制边界，不挂到每张资产表。
3. Serving 主路径改为：

```text
asset_raw_documents
  -> asset_raw_segments
  -> asset_raw_segment_relations
  -> asset_retrieval_units
```

4. `canonical` 两张表保留，但不再是 1.1 主路径。

## 当前边界

本目录当前只维护 **Knowledge Asset DB** 的共享契约。

不在这里定义：

- Mining Runtime DB
- LLM Runtime DB
- 本体 / fact / graph
- 历史版本完整视图

## 表总览

| 表 | 作用 | 说明 |
|---|---|---|
| `asset_source_batches` | 输入批次 | 记录一批输入文件夹/上传任务 |
| `asset_publish_versions` | 发布控制 | 记录哪次构建成为 active |
| `asset_batch_documents` | 批次-文档挂载 | 记录某批次发现了哪些文档 |
| `asset_raw_documents` | 文档事实源 | 当前 active 文档集合 |
| `asset_raw_segments` | 片段事实源 | 当前 active 片段集合 |
| `asset_raw_segment_relations` | 片段关系 | 用于上下文扩展 |
| `asset_retrieval_units` | 主检索入口 | Serving 默认检索对象 |
| `asset_retrieval_units_fts` | 全文索引 | SQLite FTS5 |
| `asset_retrieval_embeddings` | 向量挂载 | 预留，不是 1.1 必做 |
| `asset_canonical_segments` | 旧兼容表 | 保留但不走主路径 |
| `asset_canonical_segment_sources` | 旧兼容表 | 保留但不走主路径 |

## 设计原则

## 1. Asset 表不带 `publish_version_id`

当前 active 资产不通过“按版本过滤大表”实现，而通过发布切换实现。

因此：

- `asset_raw_documents` 不带 `publish_version_id`
- `asset_raw_segments` 不带 `publish_version_id`
- `asset_raw_segment_relations` 不带 `publish_version_id`
- `asset_retrieval_units` 不带 `publish_version_id`

## 2. `asset_publish_versions` 的职责收缩

`asset_publish_versions` 只负责：

1. 标识哪次构建成为 active
2. 记录 old active -> archived / new staging -> active
3. 记录发布历史、构建摘要、可选发布包路径

它不负责：

1. 表达每个版本完整对象集合
2. 表达每条 raw / retrieval unit 属于哪个版本

## 3. Serving 主检索入口是 `asset_retrieval_units`

Serving 1.1 不应该继续默认检索 canonical。

推荐读取链路：

```text
retrieval_units
  -> source_refs_json
  -> raw_segments
  -> raw_documents
  -> raw_segment_relations
```

## 4. `canonical` 保留但降级

为了兼容历史数据和人工排查，以下两张表仍保留：

- `asset_canonical_segments`
- `asset_canonical_segment_sources`

但它们不再代表 1.1 的主检索主链路。

## 关键字段说明

## `asset_source_batches`

记录输入身份，而不是运行时状态。

典型 `metadata_json`：

```json
{
  "default_document_type": "command",
  "batch_scope": {
    "products": ["CloudCore"],
    "product_versions": ["V100R023"],
    "network_elements": ["PGW-C"]
  },
  "tags": ["command", "core_network"]
}
```

## `asset_publish_versions`

关键字段：

- `status`: `staging / active / archived / failed`
- `base_publish_version_id`: 发布链上的上一个 active
- `source_batch_id`: 主要来源批次
- `metadata_json`: 质量门控摘要、构建统计、可选发布包路径

这张表和资产主表没有直接外键挂载关系。

## `asset_raw_documents`

当前 active 文档对象。

重点字段：

- `document_key`: 稳定文档键，通常取规范化相对路径
- `source_uri`: 实际读取位置
- `relative_path`: 相对本批次根目录路径
- `origin_batch_id`: 首次来源批次
- `processing_profile_json`: 解析/转换/抽取过程信息

## `asset_batch_documents`

用于回答：

- 某批次发现了哪些文档
- 某个文档曾出现在哪些批次

也是后续增量发现和批次级清理的基础。

## `asset_raw_segments`

片段事实源。

重点字段：

- `segment_key`
- `section_path`
- `block_type`
- `semantic_role`
- `raw_text`
- `normalized_text`
- `structure_json`
- `source_offsets_json`
- `entity_refs_json`

当前允许的 `block_type`：

```text
paragraph
heading
table
list
code
blockquote
html_table
raw_html
unknown
```

当前允许的 `semantic_role`：

```text
concept
parameter
example
note
procedure_step
troubleshooting_step
constraint
alarm
checklist
unknown
```

## `asset_raw_segment_relations`

它不是本体关系，而是篇章/上下文关系。

1.1 最小推荐关系：

```text
previous
next
same_section
same_parent_section
section_header_of
```

本版另外预留了：

```text
references
elaborates
condition
contrast
other
```

## `asset_retrieval_units`

这是 1.1 的主检索对象。

典型用途：

- `raw_text`
- `contextual_text`
- `summary`
- `generated_question`
- `entity_card`
- `table_row`

重点字段：

- `unit_key`
- `unit_type`
- `target_type`
- `target_id`
- `title`
- `text`
- `search_text`
- `facets_json`
- `entity_refs_json`
- `source_refs_json`
- `llm_result_refs_json`

要求：

- 每个可检索片段至少应有一个 retrieval unit
- `search_text` 应包含足够的上下文化检索信息

## `asset_retrieval_units_fts`

这是 SQLite FTS5 虚拟表。

通过 trigger 与 `asset_retrieval_units` 自动同步。

当前索引字段：

- `title`
- `text`
- `search_text`

## 发布与回退边界

当前 schema 只支持：

1. 当前 active 资产服务
2. 发布历史元信息记录
3. 数据来源追溯

当前 schema **不支持**：

1. 任意历史版本在线查询
2. 任意历史版本完整对象集合恢复

如果需要最低限度回退，建议在 `asset_publish_versions.metadata_json` 中记录发布包：

```json
{
  "bundle_path": "storage://asset-bundles/v11.sqlite",
  "bundle_checksum": "sha256:..."
}
```

## 本目录清理结果

`knowledge_assets` 当前只保留仍然有价值的内容：

- `schemas/`
- `dictionaries/`
- `samples/`

已废弃的空目录如 `manifests/`、`migrations/` 已移除。

## 说明

当前本目录完成的是 **共享 schema 契约切换** 和 **SQLite 基线库重建**。

Mining/Serving 代码是否已完全切到这套 1.1 主路径，是后续代码演进工作，不由本 README 自动保证。
