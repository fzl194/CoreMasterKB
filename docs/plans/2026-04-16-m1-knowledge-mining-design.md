# M1 Knowledge Mining Design

> 版本: v1.1
> 日期: 2026-04-16
> 作者: Claude Mining
> 任务: TASK-20260415-m1-knowledge-mining
> 修订说明: 基于 Codex 审查 P1-P2 修订；对齐 schema v0.4；纳入上游转换器与 manifest.jsonl；拆分 block_type/section_role；SQLite 读取共享 DDL

## 1. 目标

实现离线知识挖掘最小闭环：

```
上游转换后 Markdown / source artifacts → L0 raw_segments → L1 canonical_segments → L2 canonical_segment_sources
```

写入 staging publish version，供 Agent Serving 读取 active 版本使用。

输入不限于产品文档，也支持专家文档、项目文档、培训材料等。产品/版本/网元仅为可选 scope facet。

## 2. 核心流程

```
输入目录（带 manifest.jsonl 或纯 Markdown）
  → Ingestion（读取 manifest.jsonl 元数据 / 纯 Markdown 扫描）
  → Document Profile（识别 source_type/document_type/scope_json/tags_json）
  → Structure Parse（Markdown AST：标题/Markdown table/HTML table/代码块/列表/段落）
  → Segmentation（AST → L0 segments，拆分 block_type 与 section_role，计算 hash/normalize/simhash）
  → Canonicalization（三层去重归并 → L1 canonical + L2 source mapping）
  → Publishing（写入 staging publish version，SQLite 使用共享 DDL）
```

## 3. 模块划分

### 3.1 ingestion

文件: `knowledge_mining/mining/ingestion/`

支持两种输入模式：

**模式 A：manifest.jsonl 驱动**
- 读取输入目录中的 `manifest.jsonl`
- 每行包含 `doc_id`, `title`, `doc_type`, `nf`, `scenario_tags`, `source_type`, `path`, `note`
- 按 `path` 字段读取对应 Markdown 文件
- 输出 `RawDocumentData`，包含 manifest 元数据

**模式 B：纯 Markdown 目录**
- 递归扫描 `.md` 文件
- 解析 YAML frontmatter（如有）
- 无 manifest 时，`document_key` 由相对路径生成
- 输出 `RawDocumentData`

### 3.2 document_profile

文件: `knowledge_mining/mining/document_profile/`

以 `source_type`、`document_type`、`scope_json`、`tags_json` 为核心：

- `source_type`：从 manifest 或 frontmatter 获取（`productdoc_export`, `official_vendor`, `expert_authored`, `user_import`, `synthetic_coldstart`, `other`）
- `document_type`：从 manifest `doc_type` 或内容推断（`command`, `feature`, `procedure`, `troubleshooting`, `alarm`, `constraint`, `checklist`, `expert_note`, `project_note`, `standard`, `training`, `reference`, `other`）
- `scope_json`：产品/版本/网元等作为可选 facet，放入 scope_json
- `tags_json`：从 manifest `scenario_tags` 或内容提取

`product`、`product_version`、`network_element` 保持为兼容字段，从 `nf`（网元列表）或路径推断。

识别优先级：
1. manifest.jsonl 元数据
2. frontmatter 显式声明
3. 文件路径/目录结构推断
4. 内容模式匹配
5. 无法判断时设为默认值

### 3.3 structure

文件: `knowledge_mining/mining/structure/`

- 使用 markdown-it-py 将 Markdown 解析为 token 流
- 构建 Section 树（基于标题层级）
- 识别内容块类型：
  - 标题（heading）
  - 标准 Markdown 表格（table）
  - **原始 HTML 表格**（html_table）——识别 `<table>` 标签
  - 代码块（fence / code_block）
  - 列表（bullet_list / ordered_list）
  - 段落（paragraph）
  - 块引用（blockquote）
  - 原始 HTML（raw_html）
  - 未知结构 → 保留原文，标记 unknown
- 输出 `SectionNode` 树

### 3.4 segmentation

文件: `knowledge_mining/mining/segmentation/`

拆分 `block_type`（结构形态）和 `section_role`（语义角色）：

**block_type**（结构形态）：
- `heading`, `paragraph`, `list`, `table`, `html_table`, `table_like`, `code`, `blockquote`, `raw_html`, `unknown`

**section_role**（语义角色，通过弱规则推断）：
- `parameter`, `example`, `note`, `precondition`, `procedure_step`, `troubleshooting_step`, `concept_intro`, null（无法判断时）

切分规则：
- 每个 heading 及其后续内容块组成一个 segment group
- Markdown table 独立为一个 segment（block_type = table）
- HTML table 独立为一个 segment（block_type = html_table），保留 raw HTML
- 代码块独立为一个 segment（block_type = code）
- 其余内容合并为一个 segment（block_type = paragraph）

command_name 检测：正则匹配 `ADD|MOD|DEL|SET|DSP|LST|SHOW` + 参数名模式。

每个 segment 计算：
- `content_hash` / `normalized_hash` / `token_count`
- `section_path`（JSON 数组）
- `structure_json`（表格列数/行数等结构信息）
- `source_offsets_json`（在原文中的位置信息）

### 3.5 canonicalization

文件: `knowledge_mining/mining/canonicalization/`

三层去重归并（不变）：

| 层 | 判定条件 | relation_type | 动作 |
|---|---|---|---|
| 完全重复 | content_hash 相同 | `exact_duplicate` | 合并 |
| 归一重复 | normalized_hash 相同 | `near_duplicate` | 合并 |
| 近似重复 | simhash ≤ 3 且 Jaccard ≥ 0.85 | `near_duplicate` | 合并 |
| scope 差异 | scope_json 中 product/version/NE 不同 | `version_variant` / `product_variant` / `ne_variant` | 合并，has_variants=true |
| 其他 | 不满足上述 | `primary` | 新建 canonical |

L1 增加 `section_role` 字段（从 L0 继承）。

### 3.6 publishing

文件: `knowledge_mining/mining/publishing/`

- 创建 source_batch 记录
- 创建 staging publish_version
- 写入 raw_documents（含 scope_json, tags_json, source_type, relative_path, raw_storage_uri, structure_quality 等 v0.4 字段）
- 写入 raw_segments（含 block_type, section_role, structure_json, source_offsets_json）
- 写入 canonical_segments（含 section_role）
- 写入 canonical_segment_sources
- 切换 staging → active

## 4. 数据对象

Pipeline 内部用 dataclass 传递：

- `RawDocumentData`（ingestion 输出）— 含 manifest 元数据
- `DocumentProfile`（document_profile 输出）— 以 source_type/document_type/scope_json/tags_json 为核心
- `SectionNode` / `ContentBlock`（structure 输出）
- `RawSegmentData`（segmentation 输出）— 含 block_type + section_role
- `CanonicalSegmentData` / `SourceMappingData`（canonicalization 输出）

## 5. Dev 模式 SQLite

**不再在 `knowledge_mining/mining/db.py` 中内嵌 DDL。**

SQLite 初始化改为读取共享文件 `knowledge_assets/schemas/001_asset_core.sqlite.sql`。`db.py` 只负责：
- 连接管理
- 读取共享 SQL 文件执行建表
- 数据写入封装

SQLite 表名使用 `asset_` 前缀（与共享 DDL 一致）。

## 6. 新增依赖

```toml
dependencies = [
    "markdown-it-py>=3.0",
]
```

## 7. 测试覆盖

在原有合成 Markdown 测试基础上，新增：

| 测试 | 目标 |
|---|---|
| `test_ingest_manifest` | 读取 manifest.jsonl 并生成带元数据的 document |
| `test_ingest_plain_markdown_no_metadata` | 无 manifest 无 frontmatter 也可导入 |
| `test_parse_html_table_block` | Markdown 中保留的 `<table>` 不丢失 |
| `test_segment_block_type_and_section_role` | block 形态和语义角色分离 |
| `test_expert_document_profile` | 专家文档不需要 product/version/NE |
| `test_sqlite_schema_from_shared_file` | dev DB 使用共享 `001_asset_core.sqlite.sql` |

## 8. 不做的事

- 不做 FastAPI / Skill / 在线检索 / context pack
- 不做 PDF/Word 解析
- 不做 embedding 生成
- 不做命令抽取（M2 范围）
- 不依赖 `agent_serving` 代码
- 不从 `old/ontology` 生成 alias_dictionary
- 不在 `knowledge_mining/**` 中维护私有 asset DDL

## 9. Schema 兼容性

本任务使用 Codex 已定义的 schema v0.4（`knowledge_assets/schemas/001_asset_core.sql` 和 `001_asset_core.sqlite.sql`），不修改 schema 定义。SQLite dev 模式读取共享 `001_asset_core.sqlite.sql`。对 Serving 任务无兼容性影响。

## 10. 上游转换器适配

`cloud_core_coldstart_md/` 目录包含：
- `manifest.jsonl`：每行一个文档的元数据（doc_id, title, doc_type, nf, scenario_tags, source_type, path）
- `productdoc_to_md.py`：HTML→Markdown 转换器（M1 直接使用其输出，不调用转换器本身）
- 分类 Markdown 文档（features, commands, procedures, troubleshooting, constraints_alarms）

Ingestion 优先读取 manifest.jsonl。mapping 字段到 schema 的映射：

| manifest 字段 | 落库位置 |
|---|---|
| `doc_id` | `document_key` / `metadata_json.doc_id` |
| `doc_type` | `document_type` |
| `nf` | `scope_json.network_elements` / `network_element`（兼容字段） |
| `scenario_tags` | `tags_json` |
| `source_type` | `source_type` |
| `path` | `relative_path` |
