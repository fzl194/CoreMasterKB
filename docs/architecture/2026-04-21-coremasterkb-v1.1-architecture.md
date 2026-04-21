# CoreMasterKB v1.1 总体架构设计

> 版本：v1.1  
> 日期：2026-04-21  
> 状态：当前正式架构基线

## 0. 本轮收口来源

本文件不是凭空重写，当前正式口径来自以下几类材料收口：

1. 主讨论材料  
   - [.dev/2026-04-21-v1.1-database-complete-proposal.md](D:/mywork/KnowledgeBase/CoreMasterKB/.dev/2026-04-21-v1.1-database-complete-proposal.md)

2. 当前对外总说明  
   - [README.md](D:/mywork/KnowledgeBase/CoreMasterKB/README.md)

3. 当前数据库正式契约  
   - [databases/README.md](D:/mywork/KnowledgeBase/CoreMasterKB/databases/README.md)
   - [databases/asset_core/schemas/001_asset_core.sqlite.sql](D:/mywork/KnowledgeBase/CoreMasterKB/databases/asset_core/schemas/001_asset_core.sqlite.sql)
   - [databases/mining_runtime/schemas/001_mining_runtime.sqlite.sql](D:/mywork/KnowledgeBase/CoreMasterKB/databases/mining_runtime/schemas/001_mining_runtime.sqlite.sql)
   - [databases/agent_llm_runtime/schemas/001_agent_llm_runtime.sqlite.sql](D:/mywork/KnowledgeBase/CoreMasterKB/databases/agent_llm_runtime/schemas/001_agent_llm_runtime.sqlite.sql)

4. 历史材料，仅作背景参考，不再作为当前主链基线  
   - [docs/architecture/2026-04-15-cloud-core-agent-knowledge-architecture.md](D:/mywork/KnowledgeBase/CoreMasterKB/docs/architecture/2026-04-15-cloud-core-agent-knowledge-architecture.md)
   - `old/Self_Knowledge_Evolve/` 下的旧 demo 与设计材料

本文件与以上正式契约冲突时，以当前 `databases/` 契约和本文件的最新收口为准。

## 1. 文档目的

本文档定义 CoreMasterKB 当前正式架构基线，供 Mining、Serving、LLM 三条开发线统一对齐。

本轮架构不再沿用早期 `canonical / publish_versions / raw_documents` 主链。  
当前正式主链已经切换为：

```text
source_batch
  -> document
  -> shared snapshot
  -> document_snapshot_link
  -> raw_segments / raw_segment_relations / retrieval_units
  -> build
  -> release
  -> serving
```

本文档的目标不是保留历史讨论痕迹，而是给出当前生效的系统设计。

---

## 2. 系统目标

CoreMasterKB 不是文档搜索工具，也不是只查命令的定制后端。

它的目标是构建一套能被 Agent 作为 Skill 调用的知识后台：

```text
Agent Knowledge Backend
```

它要解决的问题包括：

1. 原始资料来源复杂  
   不仅有产品文档，还会有专家文档、项目文档，以及 Markdown、TXT、HTML、PDF、DOCX 等多种格式。

2. 查询意图复杂  
   不只是“某命令怎么写”，还包括概念解释、参数说明、操作步骤、注意事项、适用范围、差异比较、上下文扩展。

3. 输出对象是 Agent  
   返回结果不能是写死页面字段，而应是可被 Agent 消化的 Context / Evidence 包。

4. 系统会持续演进  
   当前 1.1 不是终态，而是把主干方向定对，让后续增量、个性化、LLM 增强、向量检索、GraphRAG 不需要推翻底层。

---

## 3. 总体架构

整体链路如下：

```text
Agent
  -> Skill
  -> Agent Serving
  -> asset_core
  <- Knowledge Mining
  <- Raw Documents / Source Batch

并且：
Knowledge Mining / Agent Serving
  -> agent_llm_runtime
```

### 3.1 三库边界

当前正式数据库边界是三套：

```text
asset_core
mining_runtime
agent_llm_runtime
```

#### `asset_core`

正式知识资产库，Serving 只读。

负责：

- 共享内容快照
- 原始片段与关系
- 检索单元
- build
- release

#### `mining_runtime`

Mining 运行态库。

负责：

- run
- per-document 状态
- stage event
- 断点续跑
- 失败定位

#### `agent_llm_runtime`

独立 LLM 服务运行态库。

负责：

- prompt template
- llm task
- request / attempt / result / event

### 3.2 为什么必须三库

因为这是三类完全不同的数据：

| 类别 | 代表内容 | 生命周期 | 读写模式 |
|---|---|---|---|
| 正式知识资产 | snapshot / segments / units / build / release | 长生命周期 | Mining 写，Serving 读 |
| 挖掘运行态 | run / document status / stage event | 短中生命周期 | Mining 高频写 |
| LLM 运行态 | task / request / attempt / result | 独立演进 | LLM service 主写 |

逻辑分库必须坚持。  
如果未来为了本地调试方便临时放进一个 SQLite 文件，只能视为 dev 便利，不能作为正式架构基线。

---

## 4. `asset_core` 的正式主链

`asset_core` 不是一层表，而是三层：

```text
内容对象层
  -> build 层
  -> release 层
```

### 4.1 内容对象层

核心表：

- `asset_source_batches`
- `asset_documents`
- `asset_document_snapshots`
- `asset_document_snapshot_links`
- `asset_raw_segments`
- `asset_raw_segment_relations`
- `asset_retrieval_units`
- `asset_retrieval_embeddings`（后置可选）

#### `asset_source_batches`

记录一批输入资料的身份。

#### `asset_documents`

记录逻辑文档身份。  
`document_key` 用来回答：

```text
这还是不是同一个逻辑文档
```

#### `asset_document_snapshots`

记录共享内容快照，不是文档专属快照。

这是当前架构最关键的定义之一：

```text
snapshot = 一份可被一个或多个 document 共享引用的不可变内容对象
```

它的复用边界是：

```text
normalized_content_hash
```

#### `asset_document_snapshot_links`

记录：

```text
哪个 document 在哪次输入下引用了哪份 snapshot
```

文档专属信息放在这里，例如：

- `relative_path`
- `source_uri`
- 文档级 `scope_json`
- 文档级 `tags_json`

而不是放到共享 snapshot 本体里。

#### `asset_raw_segments`

挂在共享 snapshot 下的原始事实片段。

#### `asset_raw_segment_relations`

挂在共享 snapshot 下的篇章/上下文关系。

最小必备关系：

- `previous`
- `next`
- `same_section`
- `same_parent_section`
- `section_header_of`

#### `asset_retrieval_units`

Serving 的主检索对象。

它的定位是：

```text
retrieval unit 不是去重结果
retrieval unit 是面向检索的封装视图
```

### 4.2 Build 层

核心表：

- `asset_builds`
- `asset_build_document_snapshots`

#### `asset_builds`

表示一次完整知识构建。

#### `asset_build_document_snapshots`

表示：

```text
在 build_X 中，逻辑文档 D 采用哪一份 snapshot
```

这是当前架构的第二个关键定义。

build 的粒度仍然是 document，但选择对象是 shared snapshot。

因此即使：

- 文档 A
- 文档 C

共享同一个 snapshot，build 中仍然会保留两条映射：

```text
document_A -> snapshot_S1
document_C -> snapshot_S1
```

这样同时满足：

- 内容只存一份
- 文档身份不丢
- build 仍然是文档视图

### 4.3 Release 层

核心表：

- `asset_publish_releases`

它定义：

```text
哪个 build 当前在某个 channel 上生效
```

这是当前架构的第三个关键定义。

publish 的正式语义是：

```text
release -> build
```

不是换文件，也不是日志。

---

## 5. Serving 的正式读取链路

Serving 的读取链路应为：

```text
active release
  -> build
  -> selected document snapshots
  -> retrieval_units
  -> source_refs_json
  -> raw_segments
  -> raw_segment_relations
  -> document_snapshot_links / documents
```

这意味着：

1. Serving 不直接扫全库
2. Serving 不读取 Mining runtime
3. Serving 不围绕 canonical
4. Serving 不自己决定发布边界

Serving 当前主入口应为：

```text
POST /api/v1/search
```

Serving 输出统一为：

```text
ContextPack / EvidencePack
```

外层应稳定包含：

- `query`
- `intent`
- `normalized`
- `items`
- `relations`
- `sources`
- `conflicts`
- `gaps`
- `suggested_followups`
- `debug_trace`（可选）

---

## 6. Mining 的正式职责

Mining 负责：

```text
原始资料
  -> documents / shared snapshots / links
  -> raw_segments / relations / retrieval_units
  -> build
  -> release
```

### 6.1 必须拆成两个阶段

#### Phase 1: Document Mining

输入：

- `source_batch`
- 输入文件集合

输出：

- `asset_documents`
- `asset_document_snapshots`
- `asset_document_snapshot_links`
- `asset_raw_segments`
- `asset_raw_segment_relations`
- `asset_retrieval_units`

#### Phase 2: Build & Publish

输入：

- committed snapshots
- 上一个 active release 对应 build（可选）

输出：

- `asset_builds`
- `asset_build_document_snapshots`
- `asset_publish_releases`

### 6.2 当前解析边界

当前阶段：

```text
Markdown -> raw_segments / relations / retrieval_units
TXT      -> raw_segments / relations / retrieval_units
HTML/PDF/DOC/DOCX -> 允许先建 document / snapshot / link，深度解析后置
```

当前不要求 manifest 或外部元数据文件。

---

## 7. Mining Runtime 的正式职责

`mining_runtime` 只记录过程，不承载正式知识视图。

核心表：

- `mining_runs`
- `mining_run_documents`
- `mining_run_stage_events`

### 7.1 三张表各自负责什么

#### `mining_runs`

整次 run 的总控制面。

#### `mining_run_documents`

每篇文档在本次 run 中的状态机。

#### `mining_run_stage_events`

阶段事件流水，既支持：

- 文档级阶段事件
- run 级阶段事件

因此 `mining_run_stage_events` 必须同时支持：

- `run_id`
- `run_document_id`（可空）

### 7.2 当前恢复原则

支持断点续跑，但当前采用：

```text
回到最近稳定点
```

而不是细粒度拼接半成品。

规则是：

- `committed`：跳过
- `pending`：继续处理
- `processing/failed`：清理未完成副作用后，从稳定点重做

这里必须强调：

```text
committed != published
```

`committed` 只表示文档级稳定内容对象已经落地，  
不表示它已经进入 active release。

---

## 8. LLM Runtime 的正式职责

`agent_llm_runtime` 是独立服务，不属于 Mining，也不属于 Serving。

核心表：

- `agent_llm_prompt_templates`
- `agent_llm_tasks`
- `agent_llm_requests`
- `agent_llm_attempts`
- `agent_llm_results`
- `agent_llm_events`

它的作用是：

```text
统一承接 Mining / Serving 的 LLM 调用
```

而不是让两边各自维护一套 prompt / retry / parse 逻辑。

### 8.1 当前使用原则

LLM 是增强器，不是事实源。

可用于：

#### Mining 侧

- summary generation
- generated question generation
- semantic enrichment
- entity enrichment

#### Serving 侧

- query rewrite
- intent extraction
- rerank
- context compression

资产库中只保留弱引用，例如：

- `llm_result_refs_json`

不把 LLM 运行态表直接混进 `asset_core`。

---

## 9. 开发边界

### 9.1 Mining 不该做什么

- 不要继续保留 canonical 主路径
- 不要把 Serving 的读取逻辑写死到 schema
- 不要把 LLM 输出当原始事实
- 不要要求未来语料必须带 manifest

### 9.2 Serving 不该做什么

- 不要继续把系统写成 command-only
- 不要强依赖 JSON 必有字段
- 不要把 Mining 当前实现细节当长期契约
- 不要把最终答案生成混进 Serving 主职责

### 9.3 LLM Runtime 不该做什么

- 不要直接写 `asset_core`
- 不要嵌入业务逻辑
- 不要只做“调一下模型 API”的薄封装

---

## 10. 当前有效决策

- 第一阶段正式资产主链为：

```text
source_batches
documents
document_snapshots
document_snapshot_links
raw_segments
raw_segment_relations
retrieval_units
builds
publish_releases
```

- 第一阶段只对 Markdown/TXT 生成 `raw_segments / raw_segment_relations / retrieval_units`。
- `publish_releases` 是运行态读取入口；运行态通过 active `release -> build` 读取知识视图。
- 第一阶段正式坚持逻辑分库：`asset_core / mining_runtime / agent_llm_runtime`。
- `databases/asset_core/schemas/` 是唯一 asset schema 定义源。
- `old/` 不作为 import 依赖。
- alias_dictionary 不从 `old/ontology` 生成。
- 支持 dev 模式，但 dev 便利不能反向污染正式架构。

---

## 11. 最终结论

当前 v1.1 的正式架构已经明确为：

```text
document = 逻辑文档身份
snapshot = 共享内容快照
link     = document 对 snapshot 的引用
build    = 一次完整知识视图
release  = 哪个 build 当前正式生效
```

这套架构当前能支撑：

1. 内容不重复存储
2. publish 有正式语义
3. Serving 查询边界清晰
4. Mining 过程和资产结果解耦
5. LLM 作为独立 runtime 插入
6. 后续增量、回退、个性化继续演进

后续所有执行人都应以本文档与 `databases/` 下 schema 契约为当前正式基线。
