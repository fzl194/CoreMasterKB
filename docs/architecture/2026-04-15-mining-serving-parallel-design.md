# 知识挖掘与 Agent 服务并行开发设计

> 版本：v0.3
> 日期：2026-04-17
> 作者：Codex
> 面向对象：后续两个 Claude Code 并行开发任务

## 1. 背景

当前项目目标是为云核心网知识库构建一套后端服务，使外部 Agent 能通过 Skill 查询产品文档、命令手册、配置指南中的命令写法、参数含义、配置示例、注意事项、前置条件和来源上下文。

用户已经明确新系统不再沿用旧项目“大一统 pipeline + API + ontology governance”的组织方式。旧代码已经放入 `old/`，只作为参考，不允许新代码直接 `import old.*`。

新的顶层架构是：

```text
Agent
  ↓
Skill
  ↓
Agent Serving / 知识使用态
  ↓
Knowledge Assets / 数据库知识资产桥梁
  ↑
Knowledge Mining / 知识挖掘态
  ↑
Raw Documents / 原始资料
```

这次新增的关键决策是：后续开发必须拆成两个相互独立的任务。

```text
1. 知识挖掘任务：离线生产知识资产。
2. Agent 服务任务：在线消费知识资产。
```

两边不互相调用、不共享业务函数、不互相 import。中间唯一桥梁是 `knowledge_assets` 定义的数据库资产契约。

## 2. 可行性判断

该拆分是可行的，但前提是先把数据库知识资产契约固定为共同边界。

如果两个 Claude 并行开发时各自设计表结构，最终会出现挖掘态写入的数据和运行态读取的数据对不上。因此本阶段必须遵守：

```text
knowledge_mining 不 import agent_serving。
agent_serving 不 import knowledge_mining。
两边只通过 knowledge_assets/schemas 下的数据库表结构对接。
schema 变更必须先更新契约文档，再改代码。
```

开发任务可以并行，但不能并行随意修改共享契约。共享契约一旦需要变更，必须在任务消息中说明原因、影响范围和迁移策略。

## 3. 三层知识资产模型

本系统不应把所有文档段落直接丢进检索库。当前 M1 的输入基线是普通语料文件夹递归扫描，不考虑 `manifest.jsonl`、`html_to_md_mapping.json/csv` 或其他外部元数据文件。原始语料可能来自 Markdown、TXT、HTML、PDF、DOC/DOCX、专家文档或项目文档。云核心网文档存在大量跨产品、跨版本、跨文档重复内容，例如基础知识中的 5G、APN、DNN、QoS、切片等概念会在多个产品文档中重复出现；专家文档和项目文档也可能围绕同一主题反复表达。

因此知识资产分为三层。

| 层级 | 中文名称 | 英文建议名 | 核心含义 | 默认是否检索 | 主要使用方 |
| --- | --- | --- | --- | --- | --- |
| L0 | 原始语料层 | Raw Document / Raw Segment Layer | `raw_documents` 记录所有识别到的源文件；`raw_segments` 只记录 Markdown/TXT 解析出的切片，保留章节、结构、语义、实体和来源位置 | 否 | Mining 写入，Serving 按需下钻 |
| L1 | 归并语料层 | Canonical Segment Layer | 对 L0 切片去重、归并、选主后形成的检索主对象 | 是 | Serving 主检索 |
| L2 | 来源映射与差异层 | Source Mapping & Variant Layer | 记录 L1 由哪些 L0 构成，以及 exact/normalized/near duplicate、scope variant 或 conflict candidate | 否 | Serving 用于下钻和差异判断 |

不要把 L2 叫“证据层”。旧项目中的 evidence 是为本体 fact 服务的，表示某条 subject-predicate-object 事实由哪些文本支撑。这里的 L2 不是 fact evidence，而是 canonical segment 与 raw segment 之间的来源映射和差异关系。

## 4. L0 原始语料层

L0 的职责是忠实保留原始文档切分结果，不负责合并，也不作为主检索入口。

| 维度 | 中文含义 | 示例 | 作用 |
| --- | --- | --- | --- |
| raw_segment_id | 原始语料段 ID | R001 | 唯一标识一段原始语料 |
| publish_version_id | 发布版本 ID | PV001 | 标识属于哪个资产发布版本 |
| document_id | 文档 ID | DOC001 | 关联来源文档 |
| file_type | 主输入格式 | markdown、txt、html、pdf、docx | 标识源文件物理格式 |
| source_type | 来源类型 | manual_upload、folder_scan、expert_authored | 标识来源可信度和输入方式 |
| scope_json | 适用范围 | {"product":"UDG","network_elements":["SMF"]} | 通用过滤维度，不限于产品文档 |
| tags_json | 主题标签 | ["DNN","地址池","排障"] | 召回和重排序辅助 |
| doc_type | 文档类型 | command、procedure、troubleshooting、expert_note | 判断语料业务用途 |
| section_path | 章节路径 | OM参考 / MML命令 / ADD APN / 参数说明 | 保留文档结构 |
| block_type | 结构形态 | paragraph、table、html_table、list、code | 描述这段文本来自什么结构 |
| semantic_role | 语义角色 | parameter、example、procedure_step、troubleshooting_step | 描述这段话在业务上是什么 |
| entity_refs_json | 实体引用 | [{"type":"command","name":"ADD APN"}] | 记录命令、网元、术语、特性等实体 |
| raw_text | 原始文本 | 文档原文 | 回答和追溯时使用 |
| normalized_text | 归一化文本 | 去空格、统一大小写、符号处理后的文本 | 去重使用 |
| content_hash | 原文 hash | sha256(raw_text) | 完全重复判断 |
| normalized_hash | 归一文本 hash | sha256(normalized_text) | 归一后重复判断 |
| structure_json | 结构细节 | table rows、list items、code language | 服务结构化回答 |
| source_offsets_json | 来源定位 | parser、block_index、start_line、end_line | 回溯原始来源 |

L0 回答的问题是：

```text
这段原文是什么？
它来自哪个原始来源、哪个转换产物、哪本文档、哪个章节，以及哪些可选 scope/facet？
```

## 5. L1 归并语料层

L1 是运行态检索的主对象。它不是原始事实，也不覆盖 L0，只是一个去重后的检索入口。

| 维度 | 中文含义 | 示例 | 作用 |
| --- | --- | --- | --- |
| canonical_segment_id | 归并语料段 ID | C001 | 检索命中的主对象 |
| publish_version_id | 发布版本 ID | PV001 | 标识属于哪个资产发布版本 |
| canonical_title | 归并段标题 | 5G 概念、ADD APN 参数说明 | 便于展示和召回 |
| canonical_text | 归并后文本 | 合并后的稳定表达 | Agent 默认使用的文本 |
| block_type | 主结构类型 | paragraph、table、code | 影响检索和回答模板 |
| semantic_role | 语义角色 | concept、parameter、example | 影响检索和回答模板 |
| entity_refs_json | 聚合实体 | command、network_element、term | 支持实体过滤 |
| scope_json | 适用范围 | products、product_versions、network_elements | 判断是否需要下钻 |
| has_variants | 是否存在差异 | true / false | 决定是否需要按约束下钻 |
| variant_policy | 差异处理策略 | none、require_scope、manual_review | 指导运行态如何选择 L0 |
| quality_score | 质量分 | 0.92 | 排序和质量门控 |

L1 不保存原始表格/列表/代码的完整结构细节，结构细节保留在 L0 `raw_segments.structure_json`。L1 只保存 `block_type` 和必要的结构摘要，Serving 需要精确结构时通过 L2 下钻到 primary raw segment。

## 6. L2 来源映射与差异层

L2 连接 L1 和 L0，记录归并关系和差异关系。它不是主检索对象。

| 维度 | 中文含义 | 示例 | 作用 |
| --- | --- | --- | --- |
| mapping_id | 映射 ID | M001 | 唯一标识一条映射 |
| canonical_segment_id | 归并段 ID | C001 | 指向 L1 |
| raw_segment_id | 原始段 ID | R001 | 指向 L0 |
| relation_type | 映射关系类型 | exact_duplicate、scope_variant | 说明 L0 和 L1 的关系 |
| similarity_score | 相似度分数 | 0.96 | 辅助判断归并可靠性 |
| diff_summary | 差异摘要 | V2 中参数 X 从可选变为必填 | 给 Agent 或审核使用 |
| source_priority | 来源优先级 | 100 | 多来源冲突时排序 |

`relation_type` 建议定义如下。

| relation_type | 中文含义 | 说明 | 是否可自动归并 |
| --- | --- | --- | --- |
| exact_duplicate | 完全重复 | raw_text 完全相同 | 是 |
| normalized_duplicate | 归一后重复 | 标点、空格不同，归一后相同 | 是 |
| near_duplicate | 近似重复 | 高阈值相似度判定 | 谨慎 |
| scope_variant | scope 变体 | 产品、版本、网元、项目等 scope 不同 | 不应抹平，具体维度写入 metadata_json |
| conflict_candidate | 冲突候选 | 同约束下内容矛盾 | 不自动归并 |

## 7. 挖掘态与使用态边界

| 模块 | 中文名称 | 职责 | 是否依赖对方代码 | 通过什么对接 |
| --- | --- | --- | --- | --- |
| Knowledge Mining | 知识挖掘态 | 导入 source artifacts 或上游转换后的 Markdown，生成 L0/L1/L2、写入 staging/active 资产 | 否 | 数据库 |
| Agent Serving | 知识使用态 | 面向 Skill/Agent 提供查询 API，只读 active 知识资产 | 否 | 数据库 |
| Knowledge Assets | 知识资产桥梁 | 数据库 schema、发布版本、资产表、契约文档 | 两边都依赖 | 表结构和字段语义 |

挖掘态做：

```text
Source artifacts / converted Markdown -> L0 原始语料
L0 -> L1 归并语料
L1/L0 -> L2 来源映射与差异
质量检查
发布版本
```

使用态做：

```text
Agent/Skill 请求 -> 查询约束识别
检索 L1
检查 has_variants
通过 L2 选择 L0
组装 context pack
返回给 Skill / Agent
```

使用态不做：

```text
重新解析文档
批量去重
批量归并
重新生成 canonical segment
写入 asset.* 知识资产表
```

## 8. 并行任务拆分

两个 Claude 可以并行开发，但必须遵守以下共享约束：

| 约束 | 要求 |
| --- | --- |
| 代码隔离 | Mining 不改 `agent_serving/**`；Serving 不改 `knowledge_mining/**` |
| 数据桥梁 | 两边只通过 `knowledge_assets/schemas/**` 和数据库表结构对接 |
| 发布边界 | Mining 写 staging/active 资产；Serving 只读 active 资产 |
| 测试隔离 | 两边各自有自己的 tests，不能依赖对方实现 |
| 共享变更 | schema 变更必须先改契约文档，并在任务消息中说明 |
| 禁止行为 | 禁止 `agent_serving` import `knowledge_mining`，也禁止反向 import |

### 8.1 TASK-20260415-m1-knowledge-mining

任务名称：M1 Knowledge Mining / 原始语料与归并语料生产。

任务目标：

```text
实现离线知识挖掘最小闭环：
普通语料文件夹 -> raw_documents -> Markdown/TXT raw_segments -> canonical_segments -> canonical_segment_sources。
```

允许修改范围：

```text
knowledge_mining/**
knowledge_assets/dictionaries/**
knowledge_assets/samples/**
docs/messages/TASK-20260415-m1-knowledge-mining.md
docs/plans/ 与 docs/handoffs/ 中本任务相关文件
```

谨慎修改范围：

```text
knowledge_assets/schemas/**
docs/contracts/**
```

如需修改 schema，必须先在消息中说明与 Serving 任务的兼容性影响。

禁止修改范围：

```text
agent_serving/**
skills/cloud_core_knowledge/**
```

核心子任务：

| 子任务 | 目标 | 验证方式 |
| --- | --- | --- |
| Source ingestion | 普通文件夹递归扫描，识别 md/txt/html/pdf/doc/docx | 所有支持文件都登记 raw_documents，不依赖外部元数据文件 |
| Markdown/TXT 解析 | Markdown 识别标题、表格、HTML table、代码块、列表、段落；TXT 按段落切片 | 单测输出 block_type、semantic_role、structure_json |
| 文档画像 | 识别 document_type、source_type、scope_json、tags_json；产品/版本/网元进入 scope_json | 测试批次默认参数、目录/文件名/内容推断 |
| L0 生成 | 只为 MD/TXT 生成 raw_segments | 每个 segment 有 section_path、raw_text、hash、entity_refs_json、source_offsets_json |
| L1 归并 | hash / normalized hash / simhash+jaccard 去重 | 重复概念只生成一个 canonical segment |
| L2 映射 | 建立 canonical -> raw 的来源关系 | 能表达 primary / exact_duplicate / normalized_duplicate / scope_variant |
| 写库 | 写入 staging publish_version | SQLite/Postgres 测试可查询 |

不做：

```text
FastAPI API
Agent Skill
查询意图识别
在线检索
context pack
```

提交要求：

```text
提交信息使用：[claude-mining]: ...
```

### 8.2 TASK-20260415-m1-agent-serving

任务名称：M1 Agent Serving / 归并语料检索与差异下钻。

任务目标：

```text
实现在线使用态最小闭环：
Agent/Skill 请求 -> 查询约束识别 -> 检索 L1 -> 通过 L2 下钻 L0 -> 返回 context pack。
```

允许修改范围：

```text
agent_serving/**
skills/cloud_core_knowledge/**
docs/messages/TASK-20260415-m1-agent-serving.md
docs/plans/ 与 docs/handoffs/ 中本任务相关文件
```

谨慎修改范围：

```text
knowledge_assets/schemas/**
docs/contracts/**
```

如需修改 schema，必须先在消息中说明与 Mining 任务的兼容性影响。

禁止修改范围：

```text
knowledge_mining/**
knowledge_assets/dictionaries/**
```

Serving 可以使用测试 fixture 或手写 seed 数据模拟数据库中已经存在 L0/L1/L2，不等待 Mining 实现完成。

核心子任务：

| 子任务 | 目标 | 验证方式 |
| --- | --- | --- |
| Repository | 只读 asset 表 | 测试能读取 active publish_version |
| Query Normalizer | 识别 command 及通用 scope/facet 约束 | 输入“UDG V100R023C10 ADD APN 怎么写”能提取产品/版本；专家文档问题不强制产品字段 |
| Canonical Search | 检索 L1 | 命中 canonical segment |
| Variant Resolver | 根据 L2 选择 L0 | 有版本约束时选对应 raw segment |
| Uncertainty Builder | 约束不足时返回追问建议 | ADD APN 无版本时提示需确认产品/版本 |
| Context Pack | 输出 Agent 可用结构 | 包含 answer_materials、sources、uncertainties |

不做：

```text
Markdown 解析
文档导入
去重归并
写入 asset 表
embedding 批处理
发布版本生成
```

提交要求：

```text
提交信息使用：[claude-serving]: ...
```

## 9. 最小数据库桥梁建议

本阶段不要求设计最终完整数据库，但两个并行任务至少应围绕以下桥梁对象对齐：

| 表 | 中文含义 | 写入方 | 读取方 |
| --- | --- | --- | --- |
| asset.publish_versions | 发布版本 | Mining | Serving |
| asset.documents | 文档元数据 | Mining | Serving |
| asset.raw_segments | L0 原始语料段 | Mining | Serving 下钻 |
| asset.canonical_segments | L1 归并语料段 | Mining | Serving 主检索 |
| asset.canonical_segment_sources | L2 来源映射与差异 | Mining | Serving 下钻 |
| serving.retrieval_logs | 检索日志 | Serving | Serving |
| serving.feedback_logs | Agent/用户反馈 | Serving | 后续 Mining 可选分析 |

如使用 SQLite dev mode，可以用同名逻辑表或前缀模拟 schema，例如 `asset_raw_segments`。但字段语义必须保持一致，SQLite 兼容 DDL 也应放在 `knowledge_assets/schemas/`，不得由 Mining 和 Serving 各自维护私有 asset schema。

## 10. 运行态检索逻辑

默认使用态流程：

```text
1. Agent 调用 Skill。
2. Skill 请求 Agent Serving。
3. Serving 解析查询约束：
   scope_json、entity_refs_json、document_type、block_type、semantic_role。
4. Serving 只检索 L1 归并语料层。
5. 命中 canonical segment。
6. 如果 has_variants = false：
   直接返回 canonical_text + 主要来源。
7. 如果 has_variants = true：
   通过 L2 按 scope 约束选择对应 L0。
8. 如果约束不足：
   返回不确定性和追问建议。
9. 如果存在 conflict_candidate：
   返回冲突来源，不强行回答。
```

示例：

| 用户问题 | L1 命中 | 是否下钻 | 原因 |
| --- | --- | --- | --- |
| 5G 是什么 | 5G 概念 | 通常不下钻 | 行业通用知识 |
| UDG 的 5G 概念怎么定义 | 5G 概念 | 下钻 | 用户指定产品 |
| ADD APN 命令怎么写 | ADD APN 命令 | 可能需要追问 | 命令依赖产品/版本/网元 |
| UDG V100R023C10 的 ADD APN 怎么写 | ADD APN 命令 | 下钻 | 约束完整 |
| 参数 X 是必填吗 | 参数 X 说明 | 通常下钻 | 参数可能有版本差异 |

## 11. 和 old 去重机制的关系

旧项目中的去重机制可以借鉴，但不能直接照搬。

可借鉴：

```text
1. 不删除原始数据，只标记归并关系或 superseded。
2. 使用 normalized text / hash / simhash / jaccard 判断重复。
3. 去重和冲突检测分开。
4. 保留来源，用于追溯。
```

不能照搬：

```text
1. old 的 segment 去重主要偏文档内部，新系统需要跨产品、跨版本的归并语料层。
2. old 的 evidence 服务于 fact，本阶段 L2 服务于 canonical segment 与 raw segment 映射。
3. old 的 ontology/fact 抽取不是 Phase 1A 前置目标。
4. old/ontology 不可靠，不能作为 alias_dictionary 或正式本体 seed。
```

## 12. 当前结论

后续两个 Claude 可以并行开发，但必须按以下职责拆分：

```text
Claude Mining：
  负责知识挖掘态，生产 L0/L1/L2 资产。
  提交前缀：[claude-mining]:

Claude Serving：
  负责 Agent 服务使用态，消费 L1/L2/L0 资产。
  提交前缀：[claude-serving]:
```

两者共同遵守：

```text
数据库知识资产是唯一桥梁。
代码不得互相 import。
任务提交必须区分 mining 和 serving 工作范围。
```
