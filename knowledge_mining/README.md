# Knowledge Mining

`knowledge_mining` 是 CoreMasterKB 的离线知识挖掘模块。它不提供在线 API，也不直接回答问题；它的职责是把一个普通文件夹中的原始资料扫描、解析、切片、归并，并发布成 `knowledge_assets` 约定的 SQLite 知识资产库，供 `agent_serving` 只读检索。

当前 M1 版本的核心边界是：

- 输入是一个给定文件夹，递归扫描文件夹内的文件。
- 不依赖 `manifest.jsonl`、`html_to_md_mapping.json/csv` 或其他元数据文件。
- M1 只真正解析 Markdown 和 TXT。
- HTML、PDF、DOC、DOCX 会登记到 `asset_raw_documents`，但不会生成切片。
- Mining 不 import Serving，Serving 也不 import Mining；两边只通过数据库表结构对接。
- 数据库 schema 来自 `knowledge_assets/schemas/001_asset_core.sqlite.sql`。

## 整体架构

代码主流程在 `mining/jobs/run.py`：

```text
input folder
  -> ingestion
  -> document_profile
  -> parsers
  -> segmentation
  -> canonicalization
  -> publishing
  -> SQLite asset DB
```

落库后形成三层知识资产：

| 层级 | 表 | 作用 |
|---|---|---|
| L0 原始语料层 | `asset_raw_documents`, `asset_raw_segments` | 记录原始文件和从 MD/TXT 解析出的原始片段，保留章节、结构、实体、来源位置 |
| L1 归并语料层 | `asset_canonical_segments` | 对 L0 片段去重归并后的检索主对象 |
| L2 来源映射层 | `asset_canonical_segment_sources` | 记录每个 canonical 来自哪些 raw segment，以及 primary、duplicate、variant 等关系 |
| 发布控制 | `asset_source_batches`, `asset_publish_versions` | 记录批次、版本、staging/active/archived/failed 状态 |

## 如何运行

从仓库根目录执行：

```powershell
python -m knowledge_mining.mining.jobs.run `
  --input .\data\m1_contract_corpus\corpus `
  --db .\data\m1_contract_corpus\m1_contract_asset.sqlite `
  --default-source-type folder_scan `
  --default-document-type reference `
  --scope '{"products":["CloudCore"],"product_versions":["V100R023C10"],"network_elements":["PGW-C"]}' `
  --tags "coldstart,m1"
```

最小命令：

```powershell
python -m knowledge_mining.mining.jobs.run --input .\your_folder --db .\out\asset.sqlite
```

运行成功后会输出类似：

```text
Pipeline complete: {
  'discovered_documents': 4,
  'parsed_documents': 2,
  'unparsed_documents': 2,
  'skipped_files': 0,
  'failed_files': 0,
  'raw_segments': 10,
  'canonical_segments': 8,
  'source_mappings': 10,
  'active_version_id': '...',
  'status': 'active',
  'version_code': 'pv-...'
}
```

## 输入约定

当前输入不是“固定格式产品文档”，而是普通文件夹。

示例：

```text
corpus/
  commands/
    add_apn.md
  notes/
    free5gc_register.txt
  html/
    original_page.html
  manuals/
    spec.pdf
```

支持的文件类型：

| 扩展名 | file_type | M1 是否解析出 raw_segments | 说明 |
---|---|---:|---|
| `.md`, `.markdown` | `markdown` | 是 | 使用 Markdown 结构解析器 |
| `.txt` | `txt` | 是 | 按段落和 token 窗口切片 |
| `.html`, `.htm` | `html` | 否 | 只登记 raw document |
| `.pdf` | `pdf` | 否 | 只登记 raw document |
| `.doc` | `doc` | 否 | 只登记 raw document |
| `.docx` | `docx` | 否 | 只登记 raw document |

会主动跳过的文件包括：

- `manifest.jsonl`
- `manifest.json`
- `html_to_md_mapping.json`
- `html_to_md_mapping.csv`
- `.DS_Store`
- `Thumbs.db`
- `.gitkeep`

## 批次参数

批次级信息通过 CLI 或 `BatchParams` 传入，不从元数据文件读取。

| 参数 | 对应模型字段 | 落库位置 | 含义 |
|---|---|---|---|
| `--default-source-type` | `BatchParams.default_source_type` | `asset_source_batches.source_type`, `asset_raw_documents.source_type` | 本批数据来源 |
| `--default-document-type` | `BatchParams.default_document_type` | `asset_raw_documents.document_type` | 本批默认文档类型 |
| `--scope` | `BatchParams.batch_scope` | `asset_raw_documents.scope_json`, 聚合到 `asset_canonical_segments.scope_json` | 产品、版本、网元、项目、场景、作者等通用范围 |
| `--tags` | `BatchParams.tags` | `asset_raw_documents.tags_json` | 本批标签 |
| `--chunk-size` | run 参数 | TXT parser 使用 | TXT 长段切片大小 |
| `--chunk-overlap` | run 参数 | TXT parser 使用 | TXT 长段切片重叠 token 数 |

`scope_json` 推荐使用复数字段，例如：

```json
{
  "products": ["CloudCore"],
  "product_versions": ["V100R023C10"],
  "network_elements": ["PGW-C"],
  "scenarios": ["coldstart"],
  "authors": ["expert-a"]
}
```

Serving 侧不能强依赖这些字段一定存在；Mining 侧则应尽量写入可确定的信息。

## 模块说明

### `mining/jobs/run.py`

Pipeline 编排入口。

主要函数：

| 函数 | 作用 |
|---|---|
| `run_pipeline()` | 被测试或其他 Python 代码调用，执行完整挖掘流程并返回 summary |
| `main()` | CLI 入口，解析命令行参数后调用 `run_pipeline()` |

执行顺序：

1. `ingest_directory()` 递归扫描输入目录。
2. `build_profile()` 为每个文档生成 profile。
3. `create_parser()` 按文件类型选择 parser。
4. `segment_document()` 把解析结果转成 L0 raw segments。
5. `canonicalize()` 生成 L1 canonical 和 L2 source mappings。
6. `publish()` 写入 SQLite，并激活新版本。

### `mining/ingestion/`

负责发现文件并生成 `RawDocumentData`。

它做的事：

- 递归扫描输入目录。
- 识别支持的扩展名。
- 计算文件内容 hash。
- 为 MD/TXT 读取文本内容。
- 为 HTML/PDF/DOC/DOCX 登记空 content。
- 生成稳定的 `relative_path`，并作为后续 `document_key`。
- 从批次参数继承 `source_type`、`document_type`、`scope_json`、`tags_json`。

它不做的事：

- 不读 manifest。
- 不读 frontmatter。
- 不根据内容推断产品、版本、网元。
- 不解析 HTML/PDF/DOC/DOCX 正文。

### `mining/document_profile/`

负责把 `RawDocumentData` 转成 `DocumentProfile`。

当前 M1 版本很薄，主要是统一字段：

| 输入 | 输出 |
|---|---|
| `doc.relative_path` | `profile.document_key` |
| `doc.source_type` | `profile.source_type` |
| `doc.document_type` | `profile.document_type` |
| `doc.scope_json` | `profile.scope_json` |
| `doc.tags_json` | `profile.tags_json` |
| `doc.structure_quality` | `profile.structure_quality` |
| `doc.title` | `profile.title` |

### `mining/parsers/`

按文件类型选择解析器。

| 类 | 处理类型 | 输出 |
|---|---|---|
| `MarkdownParser` | `markdown` | `SectionNode` 章节树 |
| `PlainTextParser` | `txt` | 只有段落 blocks 的 `SectionNode` |
| `PassthroughParser` | html/pdf/doc/docx/其他 | `None` |

Markdown 解析实际调用 `mining/structure/parse_structure()`。

TXT 解析逻辑：

- 先按空行切成段落。
- 小段落直接作为 paragraph block。
- 超过 `chunk_size` 的长段落按 token 边界切成多个 chunk。
- 尽量保留原始文本和标点，不用 tokens 重组文本。

### `mining/structure/`

Markdown 结构解析器，基于 `markdown-it-py`。

它先把 Markdown token 转成 `ContentBlock`，再构建 `SectionNode` 树。

识别的 block：

| block_type | 来源 |
|---|---|
| `heading` | Markdown 标题 |
| `paragraph` | 普通段落 |
| `table` | Markdown 表格 |
| `html_table` | Markdown 中保留的 `<table>` HTML 块 |
| `code` | fenced code 或 indented code |
| `list` | 有序或无序列表 |
| `blockquote` | 引用块 |
| `raw_html` | 非 table HTML 块 |

表格会尽量保留结构：

```json
{
  "kind": "markdown_table",
  "columns": ["参数标识", "参数名称", "参数说明"],
  "rows": [
    {"参数标识": "APNNAME", "参数名称": "APN 名称", "参数说明": "必选参数"}
  ],
  "row_count": 1,
  "col_count": 3
}
```

`ContentBlock.line_start` 和 `line_end` 来自 markdown-it token map，后续会进入 `source_offsets_json`。

### `mining/segmentation/`

把 `SectionNode` 树切成 L0 `RawSegmentData`。

核心原则：

- table、html_table、code、list、blockquote 独立成段。
- 普通 paragraph 在同一 section 内可以合并成一个段。
- 每段都带 `section_path`，用于保留章节上下文。
- 每段都计算 `content_hash`、`normalized_hash`、`token_count`。
- 每段尽量写入 `structure_json` 和 `source_offsets_json`。
- 每段通过插件得到 `semantic_role` 和 `entity_refs_json`。

典型 raw segment 字段：

| 字段 | 含义 |
|---|---|
| `document_key` | 来源文档，当前等于相对路径 |
| `segment_index` | 文档内片段序号 |
| `block_type` | 结构类型，如 paragraph/table/list/code |
| `semantic_role` | 语义角色，如 parameter/example/procedure_step/unknown |
| `section_path` | 章节路径数组 |
| `raw_text` | 原始片段文本 |
| `normalized_text` | 归一化文本 |
| `structure_json` | 表格/list/code 等结构细节 |
| `source_offsets_json` | parser、block_index、line_start、line_end |
| `entity_refs_json` | 命令、参数、网元等实体引用 |

### `mining/extractors.py`

定义轻量插件接口，用于把“结构解析”和“语义增强”拆开。

| Protocol | 作用 | M1 默认实现 |
|---|---|---|
| `EntityExtractor` | 从文本和结构中抽实体 | `RuleBasedEntityExtractor` |
| `RoleClassifier` | 判断片段语义角色 | `DefaultRoleClassifier` |
| `SegmentEnricher` | 丰富 canonical summary/quality | `NoOpSegmentEnricher` |

当前规则仍然很轻：

- 从文本中识别常见命令形态，如 `ADD APN`、`SHOW ...`。
- 从文本中识别常见核心网网元，如 `SMF`、`UPF`、`AMF`。
- 从参数表结构中提取 parameter 实体。
- 根据章节标题判断 `parameter`、`example`、`procedure_step`、`troubleshooting_step`、`constraint` 等角色。

后续可以替换为领域词典、NER、LLM 或本体增强，但 M1 不强依赖这些能力。

### `mining/canonicalization.py`

负责从 L0 raw segments 生成 L1 canonical segments 和 L2 source mappings。

当前是三层归并：

| 层 | 条件 | relation_type |
|---|---|---|
| 完全重复 | `content_hash` 相同 | `exact_duplicate` |
| 归一重复 | `normalized_hash` 相同 | `normalized_duplicate` |
| 近似重复 | SimHash 距离 <= 3 且 Jaccard >= 0.85 | `near_duplicate` |
| 未归并单例 | 没有重复对象 | `primary` |

每个 canonical 都必须有且只有一个 primary source。

如果同一 canonical 的来源文档 `scope_json` 不同，会标记：

- `has_variants = True`
- `variant_policy = require_scope`
- L2 mapping 的 `relation_type = scope_variant`
- mapping `metadata_json.variant_dimensions` 记录差异维度

注意：当前 canonicalization 仍是文本相似度为主，不做真正的语义冲突判断。`conflict_candidate` 是 schema 和 Serving 需要支持的关系类型，但 Mining M1 默认规则不主动生成复杂冲突判断。

### `mining/publishing/`

负责把 pipeline 结果写入 SQLite，并管理版本生命周期。

发布流程：

1. 创建 `asset_source_batches`。
2. 创建 staging 状态的 `asset_publish_versions`。
3. 写入 `asset_raw_documents`。
4. 写入 `asset_raw_segments`。
5. 写入 `asset_canonical_segments`。
6. 写入 `asset_canonical_segment_sources`。
7. 校验数据完整性。
8. 把旧 active 归档，把新版本激活为 active。
9. 提交事务。

校验内容：

- 至少有 1 条 raw document。
- 至少有 1 条 canonical segment。
- 每个 canonical 必须有且只有 1 个 primary source。
- 每个 canonical 至少有 1 个 source mapping。

如果发布失败，代码会先 rollback，避免旧 active 被破坏，然后尝试把新版本标为 failed。

### `mining/db.py`

SQLite 适配层。

它负责：

- 连接 SQLite。
- 开启 WAL 和 foreign keys。
- 读取共享 DDL：`knowledge_assets/schemas/001_asset_core.sqlite.sql`。
- 封装六张核心表的 insert。
- 封装 active version 切换。

它不维护私有 DDL。schema 变更必须先改 `knowledge_assets` 的共享契约。

### `mining/text_utils.py`

文本归一、hash、token 和相似度工具。

| 函数 | 作用 |
|---|---|
| `content_hash()` | 对原文算 SHA-256 |
| `normalize_text()` | NFKC、lower、去符号、压缩空白 |
| `normalized_hash()` | 对归一文本算 hash |
| `token_count()` | CJK-aware token 计数 |
| `simhash_fingerprint()` | 计算 SimHash |
| `hamming_distance()` | SimHash 距离 |
| `jaccard_similarity()` | token set Jaccard |

### 预留目录

这些目录当前基本为空，是后续阶段的能力预留：

| 目录 | 预期方向 |
|---|---|
| `annotation/` | 人工标注、审核、反馈闭环 |
| `command_extraction/` | 更强的命令/参数抽取 |
| `embedding/` | embedding 生成和向量索引准备 |
| `edge_building/` | 实体关系、图边构建 |
| `quality/` | 质量检查、评分、告警 |

## 数据如何入库

### raw documents

每个识别到的文件都会进入 `asset_raw_documents`，包括暂不解析的 HTML/PDF/DOC/DOCX。

重要字段：

| 字段 | 来源 |
|---|---|
| `document_key` | `relative_path` |
| `source_uri` | 本地文件路径 |
| `relative_path` | 相对输入根目录的路径 |
| `file_name` | 文件名 |
| `file_type` | 根据扩展名映射 |
| `content_hash` | 文件 bytes hash |
| `source_type` | 批次参数 |
| `document_type` | 批次参数 |
| `scope_json` | 批次参数 |
| `tags_json` | 批次参数 |
| `structure_quality` | 根据文件类型映射 |
| `processing_profile_json` | parse_status、skip_reason |

`processing_profile_json.parse_status`：

| 状态 | 含义 |
|---|---|
| `parsed` | 文件被解析并产生 raw segments |
| `skipped` | 文件已登记但未产生 raw segments |

### raw segments

只有 MD/TXT 解析后会进入 `asset_raw_segments`。

它是 Serving 下钻时最重要的来源表，因为表格 rows、list items、代码语言、行号等精确信息都在这里。

### canonical segments

`asset_canonical_segments` 是 Serving 默认检索入口。

它保存：

- 归并后的 `canonical_text`
- 用于检索的 `search_text`
- 主结构类型 `block_type`
- 主语义角色 `semantic_role`
- 聚合实体 `entity_refs_json`
- 聚合范围 `scope_json`
- 是否存在变体 `has_variants`
- 变体处理策略 `variant_policy`

### source mappings

`asset_canonical_segment_sources` 连接 canonical 和 raw segment。

Serving 应通过它判断：

- 哪个 raw segment 是 primary。
- 哪些是重复来源。
- 哪些是 scope variant。
- 哪些未来可能是 conflict candidate。

## 测试

运行 Mining 测试：

```powershell
python -m pytest knowledge_mining/tests -q
```

常用测试文件：

| 文件 | 覆盖点 |
|---|---|
| `tests/test_ingestion.py` | 文件夹扫描、跳过 manifest、文件类型识别 |
| `tests/test_parsers.py` | Markdown/TXT/Passthrough parser |
| `tests/test_structure.py` | Markdown section tree、table/list/code 解析 |
| `tests/test_segmentation.py` | raw segment 切片、结构和来源定位 |
| `tests/test_canonicalization.py` | exact/normalized/near duplicate 和 variant |
| `tests/test_publishing.py` | 发布生命周期、active 唯一性、失败处理 |
| `tests/test_pipeline.py` | 端到端混合文件夹 |
| `tests/test_corpus_verification.py` | 真实语料边界场景 |
| `tests/test_v05_fix_regression.py` | Codex review 后的回归用例 |

## 当前 M1 边界和已知限制

当前代码适合验证 M1 闭环，但不是完整生产级挖掘系统。

已知边界：

- HTML/PDF/DOC/DOCX 只登记，不解析正文。
- document_type、scope、tags 主要来自批次参数，不做复杂内容推断。
- semantic_role 和 entity_refs 是轻量规则，不是强语义理解。
- canonicalization 以文本重复和相似度为主，不做复杂冲突检测。
- 表格结构依赖 Markdown 表格或 Markdown 中保留的 HTML table；如果上游转换已经丢失表格结构，Mining 无法凭空恢复。
- source offsets 以 parser 能提供的信息为准，主要是行号和 block_index。

## 和 Serving 的关系

Mining 给 Serving 提供的是数据库资产，不提供 Python API。

Serving 应该：

- 只读取唯一 active publish version。
- 默认检索 `asset_canonical_segments`。
- 需要来源、结构、行号时通过 `asset_canonical_segment_sources` 下钻到 `asset_raw_segments`。
- 对 JSON 字段容错读取，不能要求某个 JSON 子字段必然存在。
- 把 `conflict_candidate` 与 `scope_variant` 和普通 evidence 分开处理。

Mining 应该：

- 尽量把结构化信息写进 JSON 字段。
- 保留 raw document 和 raw segment 的来源定位。
- 不为了某个 Serving 查询写专用列。
- 不修改共享 schema，除非先完成架构和兼容性讨论。

## 开发入口速查

| 想改什么 | 优先看哪里 |
|---|---|
| 增加支持的输入扩展名 | `mining/ingestion/__init__.py`, `mining/parsers/__init__.py` |
| 增强 Markdown 表格/list/code 解析 | `mining/structure/__init__.py` |
| 调整切片规则 | `mining/segmentation/__init__.py` |
| 增强实体抽取或语义角色 | `mining/extractors.py` |
| 调整去重归并策略 | `mining/canonicalization.py` |
| 调整发布版本生命周期 | `mining/publishing/__init__.py` |
| 调整落库字段 | `mining/db.py` 和 `knowledge_assets/schemas/001_asset_core.sqlite.sql` |
| 调整 CLI | `mining/jobs/run.py` |

