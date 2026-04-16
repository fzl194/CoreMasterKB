# M1 Asset Core Schema

> 当前版本：v0.3
> SQL 定义：`knowledge_assets/schemas/001_asset_core.sql`
> 适用任务：`TASK-20260415-m1-knowledge-mining`、`TASK-20260415-m1-agent-serving`

## 目标

`knowledge_assets/schemas/` 是 Knowledge Mining 和 Agent Serving 的唯一数据库契约来源。

M1 阶段采用物理快照模型：每个 `publish_version` 都是一份完整可服务知识资产快照。Mining 写入 `staging` 版本，校验通过后切换为 `active`；Serving 只读唯一 `active` 版本。

本 schema 不定义 ontology、fact、evidence。L2 表命名为 `canonical_segment_sources`，表示 L1 归并段到 L0 原始段的来源映射和差异关系，不是旧项目里的 fact evidence。

## 表总览

| 表 | 层级 | 作用 | Mining | Serving |
|---|---:|---|---|---|
| `asset.source_batches` | 输入批次 | 记录一次导入输入，不代表可服务版本 | 写入 | 审计可读 |
| `asset.publish_versions` | 发布控制 | 记录一次完整资产快照，`active` 是 Serving 入口 | 写入 / 激活 | 读取 active |
| `asset.raw_documents` | L0 文档 | 发布版本内的原始文档记录 | 写入 | 来源展示可读 |
| `asset.raw_segments` | L0 段落 | 文档切分后的原始段落 | 写入 | 下钻读取 |
| `asset.canonical_segments` | L1 归并段 | 去重归并后的主检索对象 | 写入 | 主检索 |
| `asset.canonical_segment_sources` | L2 映射 | L1 到 L0 的来源与差异映射 | 写入 | 下钻选择 |

## 版本模型

`source_batch` 和 `publish_version` 是两个不同概念。

| 概念 | 含义 |
|---|---|
| `source_batch` | 这次新来了哪些输入文件或目录 |
| `publish_version` | 这次发布后，Serving 可读取的完整知识库快照 |

M1 版本生成规则：

| 步骤 | 动作 |
|---|---|
| 1 | 读取当前唯一 `active` 版本，第一次发布时为空 |
| 2 | 创建新的 `staging` publish version，记录 `base_publish_version_id` |
| 3 | 用 `document_key + content_hash` 判断文档新增、修改、保留、删除 |
| 4 | 未变化文档可复制 L0 到新版本，记录 `copied_from_document_id` / `copied_from_segment_id` |
| 5 | 新增或修改文档重新解析生成 L0 |
| 6 | 基于新版本完整 L0 全量重建 L1 `canonical_segments` |
| 7 | 基于新版本 L1/L0 全量重建 L2 `canonical_segment_sources` |
| 8 | 校验 L0/L1/L2 完整性 |
| 9 | 事务切换旧 `active` 为 `archived`，新 `staging` 为 `active` |

同一逻辑文档在不同版本之间必须保持相同 `document_key`。`document_key` 表示“这是谁”，`content_hash` 表示“内容有没有变”。唯一约束是 `publish_version_id + document_key`，不是全局 `document_key` 唯一。

## Serving 读取规则

Serving 不读取多个版本拼接结果，也不读取 `staging`。

每次请求先确定唯一 active version：

```sql
SELECT id
FROM asset.publish_versions
WHERE status = 'active'
LIMIT 1;
```

之后所有资产查询都必须带 `publish_version_id = :active_publish_version_id`。

主路径：

```text
active publish_version
  -> asset.canonical_segments
  -> asset.canonical_segment_sources
  -> asset.raw_segments
  -> asset.raw_documents
```

产品、版本、网元等文档级约束保存在 `raw_documents`。Serving 在 L2 下钻时通过 `raw_segments.raw_document_id -> raw_documents.id` 获取这些约束，不在 L2 中重复存储。

## 字段设计边界

为避免 M1 过度冗余，当前 schema 做了以下取舍：

| 取舍 | 说明 |
|---|---|
| 文档级元信息只放 `raw_documents` | `product`、`product_version`、`network_element` 不在 `raw_segments` 和 L2 重复存储 |
| L1/L2 每个版本全量重建 | 新文档可能改变归并关系和 `has_variants` |
| L0 可物理复制 | 未变化文档可复制到新版本，保留 lineage 字段 |
| 每张资产表显式带 `publish_version_id` | 简化 Serving 查询，防止跨版本 join |
| 每张核心表保留 `metadata_json` | 给解析细节、统计、规则命中、差异详情留扩展口 |
| 不建 embedding 和 terms 表 | `segment_embeddings`、`asset_terms` 后续按需要新增，不进入 M1 core |

## 关键约束

| 约束 | 目的 |
|---|---|
| 全局最多一个 `active` publish version | Serving 始终有唯一读取入口 |
| `raw_documents(publish_version_id, document_key)` 唯一 | 同一版本内文档身份唯一 |
| `raw_segments(publish_version_id, raw_document_id, segment_key)` 唯一 | 同一文档内段落身份唯一 |
| `canonical_segments(publish_version_id, canonical_key)` 唯一 | 同一版本内 L1 归并对象唯一 |
| L2 复合外键带 `publish_version_id` | 防止 L1/L0 跨版本映射 |

## 后续扩展

M1 core 稳定后，可以新增扩展表，但不应破坏现有六张表语义：

```text
asset.segment_embeddings(canonical_segment_id, embedding_model, embedding_dim, embedding, ...)
asset.asset_terms(publish_version_id, term, normalized_term, term_type, ...)
asset.publish_validation_reports(publish_version_id, check_name, status, details_json, ...)
```

任何 schema 变更都必须先更新本目录文档，并在 Mining 与 Serving 两个任务消息文件中说明兼容性影响。
