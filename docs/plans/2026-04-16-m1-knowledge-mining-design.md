# M1 Knowledge Mining Design

> 版本: v1.0
> 日期: 2026-04-16
> 作者: Claude Mining
> 任务: TASK-20260415-m1-knowledge-mining

## 1. 目标

实现离线知识挖掘最小闭环：

```
Markdown 产品文档 → L0 raw_segments → L1 canonical_segments → L2 canonical_segment_sources
```

写入 staging publish version，供 Agent Serving 读取 active 版本使用。

## 2. 核心流程

```
Markdown 文件
  → Ingestion（文件读取、frontmatter 解析）
  → Document Profile（识别 product/version/network_element/doc_type）
  → Structure Parse（Markdown AST：标题/表格/代码块/列表/段落）
  → Segmentation（AST → L0 segments，计算 hash/normalize/simhash）
  → Canonicalization（三层去重归并 → L1 canonical + L2 source mapping）
  → Publishing（写入 staging publish version）
```

## 3. 模块划分

### 3.1 ingestion

文件: `knowledge_mining/mining/ingestion/`

- 扫描输入目录中的 Markdown 文件
- 读取文件内容
- 解析 YAML frontmatter（如有）
- 输出 `RawDocumentData` 数据对象（file_path, content, frontmatter）

### 3.2 document_profile

文件: `knowledge_mining/mining/document_profile/`

- 基于 frontmatter 字段和文件路径规则识别：
  - `product`（产品名，如 UDG, UNC, UPF）
  - `product_version`（产品版本，如 V100R023C10）
  - `network_element`（网元，如 AMF, SMF, UPF）
  - `document_type`（文档类型：command_manual, feature_guide, release_note, reference, other）
- 输出带画像的 `DocumentProfile`

识别规则：
1. frontmatter 显式声明优先
2. 文件路径/目录结构推断（如 `UDG/V100R023C10/OM参考.md`）
3. 内容模式匹配（如包含大量 MML 命令 → command_manual）
4. 无法判断时设为 `other`

### 3.3 structure

文件: `knowledge_mining/mining/structure/`

- 使用 markdown-it-py 将 Markdown 解析为 token 流
- 构建 Section 树（基于标题层级）
- 识别内容块类型：
  - 标题（heading）
  - 表格（table）
  - 代码块（fence / code_block）
  - 列表（bullet_list / ordered_list）
  - 段落（paragraph）
  - 块引用（blockquote）
- 输出 `SectionNode` 树，每个节点包含 path、level、children、content_blocks

### 3.4 segmentation

文件: `knowledge_mining/mining/segmentation/`

- 遍历 Section 树，按规则切分为 L0 segments
- 每个 segment 包含：
  - `section_path`：JSON 数组表示的章节路径
  - `section_title`：最近标题
  - `heading_level`：标题级别
  - `segment_type`：command / parameter / example / note / table / paragraph / concept / other
  - `raw_text`：原文
  - `normalized_text`：归一化文本（去空格、统一大小写、符号处理）
  - `content_hash`：sha256(raw_text)
  - `normalized_hash`：sha256(normalized_text)
  - `token_count`：token 数量（CJK 感知）
  - `command_name`：如果段落涉及命令（如 ADD APN）

切分规则：
- 每个 heading 及其后续内容块组成一个 segment group
- 表格独立为一个 segment（segment_type = table）
- 代码块独立为一个 segment（segment_type = example）
- 命令相关段落标记 command_name

### 3.5 canonicalization

文件: `knowledge_mining/mining/canonicalization/`

三层去重归并：

| 层 | 判定条件 | relation_type | 动作 |
|---|---|---|---|
| 完全重复 | content_hash 相同 | `exact_duplicate` | 合并到同一 canonical |
| 归一重复 | normalized_hash 相同 | `near_duplicate` | 合并到同一 canonical |
| 近似重复 | simhash 汉明距离 ≤ 3 且 Jaccard ≥ 0.85 | `near_duplicate` | 合并到同一 canonical |
| 版本差异 | 同 product 不同 version | `version_variant` | 合并，设 has_variants=true |
| 产品差异 | 不同 product | `product_variant` | 合并，设 has_variants=true |
| 网元差异 | 不同 network_element | `ne_variant` | 合并，设 has_variants=true |
| 其他 | 不满足上述条件 | `primary` | 新建 canonical |

L1 CanonicalSegment 生成：
- `canonical_text`：选择 primary 或最长 raw_text
- `title`：从 section_title 或 heading 提取
- `segment_type`：与 L0 一致
- `has_variants`：存在 variant 时为 true
- `variant_policy`：根据 variant 类型设置
- `search_text`：canonical_text + title 拼接，用于全文检索

L2 CanonicalSegmentSource 生成：
- 每个 L0 → L1 映射一条记录
- 第一个 L0 标记为 `is_primary = true`
- 其余标记 relation_type 和 similarity_score

### 3.6 publishing

文件: `knowledge_mining/mining/publishing/`

- 创建 source_batch 记录
- 创建 staging publish_version（base 为当前 active 或无）
- 写入 raw_documents
- 写入 raw_segments
- 写入 canonical_segments
- 写入 canonical_segment_sources
- 执行完整性校验
- 切换 staging → active

## 4. 数据对象

Pipeline 内部用 dataclass 传递，不直接操作数据库模型：

- `RawDocumentData`（ingestion 输出）
- `DocumentProfile`（document_profile 输出）
- `SectionNode` / `ContentBlock`（structure 输出）
- `RawSegmentData`（segmentation 输出）
- `CanonicalSegmentData` / `SourceMappingData`（canonicalization 输出）

## 5. Pipeline 编排

`knowledge_mining/mining/jobs/run.py` 统一编排：

```python
def run_pipeline(input_path: str, db_url: str):
    documents = ingest(input_path)
    profiles = [profile_document(doc) for doc in documents]
    all_raw_segments = []
    for doc, profile in zip(documents, profiles):
        sections = parse_structure(doc.content)
        segments = segment(sections, profile)
        all_raw_segments.extend(segments)
    canonicals, sources = canonicalize(all_raw_segments)
    publish(all_raw_segments, canonicals, sources, db_url)
```

## 6. Dev 模式 SQLite

架构文档要求 dev 用文件 SQLite（`.dev/agent_kb.sqlite`）。

M1 需要在代码中提供 SQLite 兼容建表逻辑：
- 替换 `gen_random_uuid()` 为 Python `uuid4()`
- 替换 `TIMESTAMPTZ` 为 `TEXT`（ISO 8601）
- 不使用 `pgcrypto` 扩展
- 不使用 PostgreSQL 特有的 `to_tsvector` GIN 索引

## 7. 新增依赖

```toml
dependencies = [
    "markdown-it-py>=3.0",    # Markdown AST 解析
]
```

## 8. 验证方式

用合成 Markdown 样例验证（放在 `knowledge_assets/samples/` 下）：

1. ingestion 能读取 Markdown 并提取内容
2. document_profile 能识别产品/版本/网元
3. segmentation 能生成 L0 segments，每个有 section_path、raw_text、hash
4. canonicalization 能去重，重复概念只生成一个 canonical segment
5. publishing 能写入 SQLite staging publish version 并查询

单元测试覆盖每个模块，集成测试覆盖完整 pipeline。

## 9. 不做的事

- 不做 FastAPI / Skill / 在线检索 / context pack
- 不做 PDF/Word 解析
- 不做 embedding 生成
- 不做命令抽取（M2 范围）
- 不依赖 `agent_serving` 代码
- 不从 `old/ontology` 生成 alias_dictionary

## 10. Schema 兼容性

本任务使用 Codex 已定义的 schema（`knowledge_assets/schemas/001_asset_core.sql`），不修改 schema 定义。仅在代码中提供 SQLite 兼容建表实现。
