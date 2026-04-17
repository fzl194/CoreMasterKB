# 云核心网 Agent Knowledge Backend 总体架构设计

> **版本**: v0.7 (2026-04-17)
> **审阅**: Codex 初稿 → Claude 审视修订 → Codex 边界校正 → Codex alias_dictionary 风险修正 → Codex 挖掘态/使用态并行开发拆分

## 1. 文档目的

本文档沉淀当前项目的新架构基线，供 Claude Code 后续制定实现计划和开发使用。

当前仓库已将旧项目完整代码移动到 `old/`。旧代码不再作为新系统的直接运行入口，只作为参考实现和可剥离资产来源。新系统不应继续沿用旧项目”大一统 pipeline + API + ontology governance”的组织方式，而应按真实业务使用链路重新设计。

本项目的新目标是构建一套面向云核心网知识使用的后端体系，使 Agent 能通过 Skill 调用后端服务，查询云核心网产品文档、命令手册、配置指南中的命令写法、参数含义、配置示例、注意事项、前置条件和来源证据。

### 修订记录

| 日期       | 来源   | 变更摘要                                                                 |
| ---------- | ------ | ---------------------------------------------------------------------- |
| 2026-04-15 | Codex  | 初稿：五层架构、目录结构、里程碑 M0-M8                                    |
| 2026-04-15 | Claude | 审视修订：单 pyproject.toml、补充 Query Normalizer、合并里程碑、补充 dev mode、answer_materials 子结构、alias_dictionary 来源、schema 治理权 |
| 2026-04-15 | Codex  | 边界校正：修正 dev SQLite 共享问题、统一运行入口、补充根目录 scripts、修正 alias_dictionary 来源、细化 M3 子任务 |
| 2026-04-15 | Codex  | alias_dictionary 风险修正：old/ontology 不可靠，不作为正式 alias 来源；M0 改为规则占位；正式 alias 从用户导入的 Markdown 文档中抽取 |
| 2026-04-15 | Codex  | 明确 Knowledge Mining 与 Agent Serving 独立开发，以数据库知识资产为唯一桥梁；新增 L0/L1/L2 资产分层与并行任务边界 |
| 2026-04-16 | Codex  | schema v0.4：引入通用 source artifact 视角，支持 Markdown/HTML/PDF/DOC 等来源；产品/版本/网元降级为可选 scope/facet；纳入 productdoc_to_md.py 上游转换链路 |
| 2026-04-17 | Codex  | schema v0.5：M1 输入收敛为普通文件夹递归扫描，不考虑外部元数据文件；M1 只解析 Markdown/TXT；raw/canonical 字段统一为 block_type、semantic_role、entity_refs_json、scope_json |

本轮并行开发上下文详见：

```text
docs/architecture/2026-04-15-mining-serving-parallel-design.md
```

## 2. 核心共识

整体架构按以下链路组织：

```text
Agent
  ↓
Skill
  ↓
Agent Serving / 运行态服务
  ↓
Knowledge Assets / 知识资产层
  ↑
Knowledge Mining / 挖掘态服务
  ↑
Raw Documents / 原始资料
```

关键原则：

- Agent 层依赖已有 Agent 框架，不在本项目内重做。
- Skill 层保持轻量，只负责工具封装、调用策略、回答格式和追问规则。
- Agent Serving 是运行态，只读已发布知识资产，面向 Skill 提供业务语义化 API。
- Knowledge Assets 是中间产物契约，挖掘态写入，运行态读取。
- Knowledge Mining 是设计态/挖掘态，负责从原始资料生产知识资产。
- `old/` 只读参考，新代码不得 `import old.*`。

## 3. 分层职责

### 3.1 Agent 层

Agent 层由外部已有 Agent 框架承载。

职责：

- 理解用户问题。
- 判断是否需要调用云核心网知识 Skill。
- 根据 Skill 返回的 context pack 组织最终答案。
- 在厂家、产品、版本、EPC/5GC 场景缺失时追问或提示不确定性。

不负责：

- 直接查询数据库。
- 直接访问向量索引。
- 直接执行图遍历。
- 理解挖掘 pipeline 的内部实现。

### 3.2 Skill 层

Skill 是 Agent 与后端服务之间的轻量契约。

职责：

- 定义可调用工具。
- 描述何时调用哪个工具。
- 约束回答模板。
- 处理缺失上下文的追问规则。
- 将 Agent 的自然语言意图转为后端 API 请求。

第一版 Skill 至少包含：

```text
get_command_usage
search_cloud_core_knowledge
assemble_cloud_core_context
```

Skill 不做：

- 文档检索实现。
- 重排序。
- 图扩展。
- 数据库访问。
- 批量知识加工。

### 3.3 Agent Serving / 运行态服务

运行态服务是 Skill 调用的在线后端。

职责：

- 查询归一化。
- 简单意图判断。
- 检索计划生成。
- 多路召回。
- 上下文扩展。
- 重排序。
- context pack 组装。
- 证据返回。
- 检索日志和调试解释。

运行态服务只读 `Knowledge Assets` 中 active publish version 的数据。

运行态服务只允许写：

```text
retrieval_logs
feedback_logs
```

运行态不做：

- 文档解析。
- 命令抽取。
- 批量 embedding 生成。
- 质量门控。
- 发布版本切换。
- 人工修正。

### 3.4 Knowledge Assets / 知识资产层

知识资产层是系统最关键的中间契约。

它承载挖掘态产出的可发布数据，并为运行态提供稳定读取模型。

M1 的核心资产包括：

```text
publish_versions
source_batches
raw_documents
raw_segments
canonical_segments
canonical_segment_sources
```

核心要求：

- 所有在线查询必须基于某个 publish version。
- 默认读取 `status = active` 的版本。
- 挖掘态不得直接覆盖线上 active 资产。
- 新资产先进入 staging，通过质量检查后再激活。
- 运行态默认检索 `canonical_segments`，只在需要产品/版本/网元下钻时通过 `canonical_segment_sources` 读取 `raw_segments`。

阶段 1A 的语料资产分为三层：

| 层级 | 中文名称 | 核心含义 | 默认是否检索 |
| --- | --- | --- | --- |
| L0 | 原始语料层 | `raw_documents` 记录所有识别到的源文件；`raw_segments` 只记录 Markdown/TXT 解析出的切片，保留章节、结构、语义、实体和来源位置 | 否 |
| L1 | 归并语料层 | `canonical_segments` 对 L0 切片去重、归并、选主后形成的检索主对象 | 是 |
| L2 | 来源映射与差异层 | `canonical_segment_sources` 记录 L1 由哪些 L0 构成，以及 exact/normalized/near duplicate、scope variant 或 conflict candidate | 否 |

L2 不命名为 evidence。旧项目中的 evidence 服务于本体 fact，本阶段 L2 服务于 `canonical_segment -> raw_segment` 的来源映射与差异选择。

### 3.5 Knowledge Mining / 挖掘态服务

挖掘态服务负责从原始资料生产知识资产。

阶段 1A 只聚焦命令与证据优先，不做完整本体抽取。

职责：

- 原始文档接入。
- 文档画像识别。
- 章节结构恢复。
- segment 切分。
- 轻量 segment 标注。
- 命令入口抽取。
- 命令到参数/示例/注意事项/前置条件段落的关联。
- segment edge 构建。
- embedding 批量生成。
- 质量检查。
- 发布版本生成。

M1 解析器边界：

```text
Markdown -> raw_segments
TXT      -> raw_segments
HTML/PDF/DOC/DOCX -> 只登记 raw_documents，不生成 raw_segments
```

PDF、Word、HTML 深度解析后置，但 schema 必须能登记这些原始来源。M1 不考虑 `manifest.jsonl`、`html_to_md_mapping.json/csv` 或其他外部元数据文件；Mining 只能基于文件夹递归扫描、文件后缀、相对路径、目录结构、文件名和文件内容做识别与推断。

## 4. 推荐目录结构

> **Claude 审视修订**: 阶段 1A 采用单 `pyproject.toml` + 目录隔离，而非独立 Python 包。理由：内网单机部署，两个独立包增加依赖管理和部署成本，数据库 schema 隔离已提供足够的运行态边界。后续如需独立部署再拆包。

建议根目录组织如下：

```text
Self_Knowledge_Evolve/
  pyproject.toml                    # 单一项目配置，统一依赖管理
  .env.example
  scripts/                          # 跨层运维脚本
    init_db.py                      # 统一初始化 mining/asset/serving schema
    run_dev_demo.py                 # 可选：同进程最小 demo runner

  docs/
    architecture/                   # 架构设计文档（本文件所在目录）
    messages/
    plans/
    handoffs/
    analysis/

  old/
    ...旧项目完整代码，只读参考...

  knowledge_mining/                 # 挖掘态：文档加工 pipeline
    mining/
      ingestion/                    # P1 文档接入
      document_profile/             # P2 文档画像识别
      structure/                    # P3 章节结构恢复
      segmentation/                 # P4 segment 切分
      annotation/                   # P5 segment 轻量标注
      command_extraction/           # P6 命令抽取
      edge_building/                # P7 关系构建
      embedding/                    # P8 embedding 生成
      quality/                      # P9 质量门控
      publishing/                   # P10 发布版本生成
      jobs/                         # pipeline 编排与任务调度
    scripts/
      run_mining.py                 # 挖掘态入口脚本
    tests/

  knowledge_assets/                 # 知识资产层：schema + 静态资产
    schemas/                        # 唯一 schema 定义源（见 §4.1）
      init_asset.sql
      init_mining.sql
      init_serving.sql
    migrations/                     # schema 版本迁移
    dictionaries/                   # alias_dictionary YAML（见 §4.2）
    manifests/                      # publish version 清单
    samples/                        # 评测集（见 §4.3）

  agent_serving/                    # 运行态：在线检索服务
    serving/
      api/                          # FastAPI 路由
        command_usage.py            # POST /api/v1/command/usage
        search.py                   # POST /api/v1/search
        context_assemble.py         # POST /api/v1/context/assemble
        health.py                   # GET /health
        debug.py                    # POST /debug/retrieve, /debug/explain
      application/                  # 业务编排
        normalizer.py               # 查询归一化（见 §4.4）
        planner.py                  # 检索计划生成
        assembler.py                # context pack 组装
      retrieval/                    # 多路召回
        exact_command.py
        title_search.py
        keyword_search.py
        vector_search.py
        metadata_filter.py
      expansion/                    # 上下文扩展
        edge_expander.py
      rerank/                       # 重排序
        command_reranker.py
      evidence/                     # 证据打包
        evidence_builder.py
      schemas/                      # request/response 模型
      repositories/                 # 数据访问层
      observability/                # 日志、指标
    scripts/
      run_serving.py                # 运行态入口脚本
    tests/

  skills/                           # Skill 层：Agent 工具定义
    cloud_core_knowledge/
      SKILL.md                      # Skill 主描述
      tools.md                      # 工具定义与选择策略
      answer_templates.md           # 回答模板
      followup_rules.md             # 追问规则
      examples.md                   # 示例问题与预期回答
```

如果 Claude 第一轮需要降低工程复杂度，可以先创建目录骨架和 README，不必一次性填满所有模块。

### 4.1 Schema 治理权

`knowledge_assets/schemas/` 是**唯一 schema 定义源**。

- Mining 和 Serving 都从这里读取表结构定义。
- Schema 变更必须通过 migration 文件记录，由根目录脚本 `scripts/init_db.py` 统一执行。
- Mining 和 Serving 均不得自行创建或修改 asset 表结构。

### 4.2 alias_dictionary 数据来源

> **Codex 风险修正 (v0.4)**: `old/ontology` 中的云核心网本体不可靠，不能作为正式 alias_dictionary 的来源。

阶段 1A 的 alias_dictionary 策略：

- **系统不依赖预置本体或旧 alias 字典启动。**
- 用户运行时导入 source artifacts 后，系统基于上游转换结果、Markdown/HTML 标题、表格、代码块、列表和弱规则自动生成可检索的 section、segment、命令候选、术语候选和上下文扩展边。
- 正式 alias_dictionary 不是 Phase 1A 的前置输入，而是后续从用户导入的产品文档中抽取候选、经人工确认后形成的知识资产。
- M0 阶段只创建规则配置占位文件（command_patterns.yaml、section_patterns.yaml、term_patterns.yaml、builtin_alias_hints.yaml），不生成正式 alias_dictionary。
- `old/ontology` 只能作为参考候选源，不能作为默认 seed，更不能默认加载到 `asset.alias_dictionary`。
- Mining 第一版可以直接使用上游转换好的 Markdown，但必须把输入抽象为 source artifact，不得依赖某一份固定文档格式或 frontmatter。产品/版本/网元只是可选 scope/facet，不是所有语料的必填主轴。

### 4.2.1 Source Artifact 与通用 scope

原始语料可能来自 Markdown、TXT、HTML、PDF、DOC/DOCX、专家手写文档或项目交付文档。schema v0.5 使用以下原则：

- `raw_documents.file_type` 记录主输入格式：`markdown/html/pdf/doc/docx/txt/other`。
- `raw_documents.source_uri` 记录后端实际读取位置，`relative_path` 记录相对本批次输入根目录路径。
- `raw_documents.content_hash` 必须来自文件内容，不得使用路径 hash。
- `raw_documents.scope_json` 记录产品、版本、网元、项目、作者、环境、客户、专题等可选适用范围；产品/版本/网元不再作为外层字段。
- `raw_documents.tags_json` 记录主题、场景和对象标签。
- `raw_documents.processing_profile_json` 记录 parser、normalization、extraction quality 等处理过程。
- `raw_documents.metadata_json` 记录 `parse_status/skip_reason/inferred_by` 等状态。
- `raw_segments.block_type` 记录结构形态：paragraph/list/table/html_table/code/raw_html/unknown。
- `raw_segments.semantic_role` 记录语义角色：concept/parameter/example/note/procedure_step/troubleshooting_step/constraint/alarm/checklist/unknown。
- `raw_segments.entity_refs_json` 记录命令、网元、术语、特性等通用实体引用。
- `canonical_segments` 与 `raw_segments` 使用同一套 `block_type/semantic_role/entity_refs_json/scope_json` 语义，Serving 以 canonical 为主检索入口。

### 4.3 评测集位置

M7 的 30-50 个真实问题评测集存放在 `knowledge_assets/samples/eval_questions.yaml`。

### 4.4 Query Normalizer 模块

> **Claude 审视补充**: 这是检索质量的基石，CoreMaster.md 表 19 已明确定义，需要在架构中显式存在。

Query Normalizer（`serving/application/normalizer.py`）负责：

| 功能         | 阶段 1A 实现方式        | 示例                      |
| ------------ | ---------------------- | ------------------------- |
| 操作词归一化 | 规则字典               | 新增 → ADD，修改 → MOD    |
| 术语归一化   | alias_dictionary       | APN ↔ DNN，N4 ↔ PFCP     |
| 命令实体识别 | 模式匹配 + dictionary  | 识别 `ADD APN`            |
| 过滤条件抽取 | 规则                   | 识别版本、厂家、EPC/5GC   |
| 缺失项识别   | 规则                   | 无厂家/版本时返回 uncertainty |

## 5. 数据库边界

阶段 1A 建议使用同一个 PostgreSQL，通过 schema 隔离职责：

```text
mining.*
asset.*
serving.*
```

建议：

- `mining.*` 放挖掘过程中的 staging/intermediate 数据。
- `asset.*` 放发布后的稳定知识资产。
- `serving.*` 放运行态日志和反馈。

不建议第一阶段拆多个数据库，避免运维复杂度过高。

## 6. Phase 1A 范围

Phase 1A 是最小可用闭环，不是完整系统。

目标：

```text
用少量云核心网文档，让 Agent 通过 Skill 查询命令写法、参数、示例、注意事项和来源证据。
```

必做：

- 项目目录骨架。
- Asset schema 初版。
- Markdown/HTML/TXT 文档导入。
- section/segment 生成。
- 命令入口索引。
- command 到 parameter/example/note/condition segment 的关联。
- segment_edges。
- segment embedding。
- `/api/v1/command/usage`。
- `/api/v1/search`。
- `/api/v1/context/assemble`。
- Skill 初版文档。
- 30-50 个真实问题评测集。

不做：

- 复杂 PDF/Word 解析。
- 完整 ontology。
- facts/triples。
- Neo4j 依赖。
- 影响分析。
- 故障专家推理。
- 人工审批流。
- Dashboard。
- 旧项目完整 worker 机制。

## 7. Graph-RAG 第一阶段定义

阶段 1A 的 Graph-RAG 不使用大图作为强依赖，也不要求 Neo4j。

它通过关系表实现：

```text
asset.segment_edges
asset.command_segment_links
asset.sections
```

典型扩展逻辑：

```text
命中 command_def
  → 扩展 command_to_parameter
  → 扩展 command_to_example
  → 扩展 command_to_note
  → 扩展 command_to_condition
  → 扩展 same_section / prev_next
```

阶段 1A 中 Graph-RAG 的价值不是展示图，而是让 Agent 获取完整上下文和证据组合。

## 8. 运行态 API 初版

### 8.1 `POST /api/v1/command/usage`

处理：

```text
ADD APN 命令怎么写？
ADD APN 的参数是什么意思？
有没有配置示例？
这个命令有什么注意事项？
```

返回 context pack，而不是裸搜索结果。

### 8.2 `POST /api/v1/search`

通用兜底检索。

适用：

- 命令索引未覆盖。
- 术语解释。
- 模糊问题。
- Skill fallback。

### 8.3 `POST /api/v1/context/assemble`

给定候选 command/segment/document，重新组装稳定上下文包。

适用：

- 多步 Skill 调用。
- 二次收束。
- 后续流程类/故障类接口复用。

### 8.4 Context Pack 最小字段

运行态返回给 Skill 的核心结构应稳定：

```text
query
intent
normalized
key_objects
answer_materials
evidence
source_documents
uncertainties
suggested_followups
debug_trace
```

`debug_trace` 默认仅 debug 模式返回。

### 8.5 answer_materials 子结构

> **Claude 审视补充**: 这是 Skill 层和 Serving 层的接口契约，越早定稳越好。来自 CoreMaster.md 表 24。

```text
answer_materials:
  command_candidates: [...]      # 候选命令列表
  template: "..."                # 命令模板/格式
  parameters: [...]              # 参数说明列表
  examples: [...]                # 配置示例
  notes: [...]                   # 注意事项
  preconditions: [...]           # 前置条件
  applicability:                 # 适用范围
    vendor: "..."
    product: "..."
    version: "..."
  related_terms: [...]           # 相关术语（如 APN/DNN）
  confidence_summary: "..."      # 整体可信度概述
```

对于非命令类问题（通用检索、流程、故障等），`answer_materials` 的子字段按 intent 不同而变化，但外层 context pack 结构保持不变。

## 9. old 代码剥离策略

`old/` 是参考库，不是运行依赖。

禁止：

```text
from old...
import old...
```

可参考或瘦身迁移：

```text
old/src/pipeline/preprocessing/extractor.py
old/src/pipeline/preprocessing/normalizer.py
old/src/utils/hashing.py
old/src/utils/text.py
old/src/utils/embedding.py
old/src/providers/postgres_store.py
old/src/providers/bge_m3_embedding.py
old/scripts/init_postgres.sql 中 documents / segments / t_rst_relation 思路
old/demo/run_text_to_ontology.py 的内存 demo 思路
```

暂不迁移：

```text
old/src/governance/*
old/src/stats/*
old/src/ontology/*
old/src/operators/*
old/src/api/semantic/*
old/src/pipeline/stages/stage3_align.py 之后的完整本体链路
old/worker.py
old/static/*
```

## 10. 里程碑

Claude Code 后续计划建议按以下里程碑展开。M0 之后拆分为知识挖掘态与 Agent 服务使用态两条线。两条线可以并行开发，但必须以 `knowledge_assets/schemas/` 和契约文档作为唯一桥梁。

### M0 项目骨架

- 创建 `knowledge_mining/`、`knowledge_assets/`、`agent_serving/`、`skills/` 目录骨架。
- 建立单一 `pyproject.toml` + 依赖配置。
- `agent_serving` 提供 `GET /health`。
- 创建规则配置占位（command_patterns.yaml、section_patterns.yaml、term_patterns.yaml、builtin_alias_hints.yaml）和 Markdown 语料入口（corpus_seed/）。不生成正式 alias_dictionary。
- **验证**: `python -m agent_serving.scripts.run_serving` 能启动，`curl /health` 返回 200。

### M1A Knowledge Mining / 知识挖掘态

- 独立任务 ID：`TASK-20260415-m1-knowledge-mining`。
- 只负责离线生产知识资产。
- 支持普通文件夹递归扫描，登记 Markdown/TXT/HTML/PDF/DOC/DOCX 等 source artifacts。
- 只对 Markdown/TXT 生成 L0 `raw_segments`；HTML/PDF/DOC/DOCX 当前只登记 `raw_documents`。
- 基于 content hash / normalized hash / 高阈值近似规则生成 L1 归并语料层。
- 生成 L2 来源映射与差异层，表达 primary / exact_duplicate / normalized_duplicate / near_duplicate / scope_variant / conflict_candidate。
- 写入 staging publish version。
- 不做 FastAPI、Agent Skill、在线检索、context pack。
- 提交信息使用 `[claude-mining]: ...`。

### M1B Agent Serving / 知识使用态

- 独立任务 ID：`TASK-20260415-m1-agent-serving`。
- 只负责在线消费已发布知识资产。
- 读取 active publish version。
- 默认检索 L1 `canonical_segments`。
- 当 `has_variants = true` 或用户给出产品、版本、网元、项目、作者、场景等 scope 约束时，通过 L2 下钻 L0。
- 输出 Agent 可用的 context pack、uncertainties、suggested_followups。
- 不做 Markdown 解析、文档导入、去重归并、写入 asset 表。
- 提交信息使用 `[claude-serving]: ...`。

### M2 命令索引与上下文扩展

- 命令入口索引：识别 `ADD/MOD/DEL/SET/SHOW/LST/DSP` 等命令 → commands + command_aliases + command_segment_links。
- 上下文扩展边：生成 segment_edges（prev_next, same_section, command_to_parameter, command_to_example, command_to_note, command_to_condition）。
- 向量资产：批量生成 segment embedding。
- 发布门控：质量门控检查（命令抽取命中率 > 80%，空 segment < 2%），通过后激活发布版本。
- **验证**: 给定命令名 `ADD APN`，能通过 command_segment_links 找到其参数段、示例段、注意事项段，并通过 segment_edges 扩展上下文。

### M3 Serving 检索引擎

- exact command retriever。
- title retriever。
- keyword retriever（FTS/BM25）。
- vector retriever。
- metadata filter（vendor/product/version）。
- expansion engine（基于 segment_edges + command_segment_links）。
- command reranker（按命令类排序函数）。
- **验证**: `/debug/retrieve` 接口能展示多路召回结果和排序分数。

### M4 Context Pack 与业务 API

- `POST /api/v1/command/usage` 输出稳定 context pack。
- `POST /api/v1/search` 通用兜底检索。
- `POST /api/v1/context/assemble` 二次组装。
- 实现 sources、uncertainties、suggested_followups。
- **验证**: 给定 `ADD APN 命令怎么写`，返回完整的 context pack，包含 command_candidates、parameters、examples、notes、sources、uncertainties。

### M5 Skill 初版

- `skills/cloud_core_knowledge/SKILL.md`。
- 工具定义（get_command_usage, search_cloud_core_knowledge, assemble_cloud_core_context）。
- 调用策略（命令类 → get_command_usage，模糊 → search）。
- 回答模板（适用场景/命令模板/参数说明/示例/注意事项/来源/需要确认信息）。
- 追问规则（缺厂家/版本/EPC-5GC 时先给通用答案再提示）。
- 示例问题。
- **验证**: Skill 文档可被 Agent 框架加载并正确路由工具调用。

### M6 评测闭环

- 准备 30-50 个真实问题（`knowledge_assets/samples/eval_questions.yaml`）。
- 评估命令召回率、来源覆盖率、context pack 完整性。
- 根据评测结果调优 reranker 权重和扩展策略。
- **验证**: 核心命令类问题召回率 > 80%，context pack 关键字段非空率 > 90%。

## 11. 开发模式

> **Claude 审视补充**: 旧项目的 dev mode 是非常有价值的开发体验，新架构应延续。

阶段 1A 支持两种运行模式：

### 11.1 开发模式（dev）

- 文件 SQLite 替代 PostgreSQL，默认路径为 `.dev/agent_kb.sqlite`。
- 内存向量索引替代 pgvector。
- 无需 PostgreSQL、Ollama 等外部服务。
- 通过 `python -m agent_serving.scripts.run_serving` 启动运行态。
- 通过 `python -m knowledge_mining.mining.jobs.run` 运行挖掘态（M2+ 实现）。
- 可选提供 `python scripts/run_dev_demo.py`，在同一进程中完成最小文档导入、资产 seed 和接口 smoke test。
- 适合本地开发和快速验证。

说明：不要使用 SQLite `:memory:` 作为默认 dev 存储。Mining 和 Serving 通常是两个进程，`:memory:` 无法跨进程共享数据，会导致挖掘态写入后运行态读不到资产。若需要纯内存模式，只允许在同进程 demo runner 中使用。

### 11.2 生产模式（prod）

- PostgreSQL + schema 隔离（mining/asset/serving）。
- pgvector 向量检索。
- Ollama bge-m3 embedding。
- 内网单机部署。

通过环境变量 `APP_ENV=dev|prod` 切换，repository 层根据模式选择不同的数据访问实现。

## 12. 需要 Claude 重点避免的问题

- 不要把 mining pipeline 和 serving API 混在同一个运行服务里。
- 不要让 serving import mining。
- 不要让 mining import serving。
- 不要把旧项目完整复制回来。
- 不要第一阶段引入完整 ontology / facts / Neo4j。
- 不要把 Skill 写成重型检索系统。
- 不要先做 PDF/Word 复杂解析而阻塞命令问答闭环。
- 不要返回裸搜索结果给 Agent，必须稳定 context pack。
- 不要让 mining 和 serving 各自定义 schema，schema 定义权归 `knowledge_assets/schemas/`。
- 不要在并行任务中跨范围修改代码：Mining 任务不改 `agent_serving/**`，Serving 任务不改 `knowledge_mining/**`。

## 13. 当前有效决策

- 第一阶段只做 Phase 1A 最小闭环。
- 第一阶段聚焦命令与证据优先。
- 第一阶段 Mining 输入基线为普通语料文件夹递归扫描，不考虑外部元数据文件；schema 支持 Markdown/HTML/PDF/DOC/DOCX/TXT 等原始来源记录。
- 第一阶段只解析 Markdown/TXT 生成 raw_segments；HTML/PDF/DOC/DOCX 只登记 raw_documents，后续按文件类型增加 parser。
- 第一阶段 Graph-RAG 使用关系表实现，不强依赖 Neo4j。
- 第一阶段使用同库不同 schema。
- 第一阶段采用单 `pyproject.toml`，mining 和 serving 通过目录隔离，不拆独立包。
- `publish_versions` 是运行态读取入口。
- `old/` 不作为 import 依赖。
- `knowledge_assets/schemas/` 是唯一 schema 定义源。
- alias_dictionary 不从 `old/ontology` 生成。系统不依赖预置本体启动，正式 alias 从用户导入的 source artifacts 中抽取（M2/M3）。M0 只创建规则配置占位。
- 支持 dev 模式（文件 SQLite + 内存向量索引），降低开发环境依赖。
- 评测集存放在 `knowledge_assets/samples/eval_questions.yaml`。
- M0 之后拆分为 `TASK-20260415-m1-knowledge-mining` 与 `TASK-20260415-m1-agent-serving` 两个可并行任务。
- Mining 与 Serving 通过数据库知识资产契约对接，代码不得互相 import。
- 后续 Claude 提交必须区分工作范围：挖掘态使用 `[claude-mining]: ...`，使用态使用 `[claude-serving]: ...`。
