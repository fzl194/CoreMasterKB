# Mining / Serving 检索单元协同说明

- 日期：2026-04-25
- 作者：Codex
- 主题：当前 `knowledge_mining` 与 `agent_serving` 围绕检索单元（`retrieval_unit`）的协同方式说明

---

## 1. 文档目的

本文档回答三个问题：

1. 当前 Mining 已经把哪些检索单元生产出来了。
2. 当前 Serving 如何消费这些检索单元完成 `/search`。
3. 当前两边协同的核心合同、边界和未完全收口的部分是什么。

本文档基于以下现状材料整理：

- `docs/plans/2026-04-21-v11-knowledge-mining-impl-plan.md`
- `docs/plans/2026-04-22-v12-agent-serving-impl-plan.md`
- `docs/messages/TASK-20260421-v11-knowledge-mining.md`
- `docs/messages/TASK-20260421-v11-agent-serving.md`
- `knowledge_mining/mining/jobs/run.py`
- `knowledge_mining/mining/retrieval_units/__init__.py`
- `agent_serving/serving/api/search.py`
- `agent_serving/serving/application/assembler.py`
- `agent_serving/serving/retrieval/bm25_retriever.py`
- `agent_serving/serving/pipeline/query_planner.py`
- `databases/asset_core/schemas/001_asset_core.sqlite.sql`

---

## 2. 一句话总览

当前 Mining / Serving 的协同主轴已经不是“文档”，而是：

`raw_segment -> retrieval_unit -> serving retrieval candidate -> source drill-down -> context expansion -> ContextPack`

其中：

- Mining 负责把文档切成 `raw_segment`，再把 segment 生产成多个 `retrieval_unit`。
- Serving 负责先检索 `retrieval_unit`，再通过 `source_segment_id / source_refs_json / target_ref_json` 下钻回 `raw_segment` 和 relations。
- `raw_segment` 是内容真相源，`retrieval_unit` 是检索入口层，`ContextPack` 是 Serving 对 Agent 的交付层。

---

## 3. 当前协同的整体链路

### 3.1 Mining 侧产出链路

当前 Mining 的正式主链在 `knowledge_mining/mining/jobs/run.py` 中已经落地为：

`ingest -> parse -> segment -> enrich -> build_relations -> build_retrieval_units -> select_snapshot -> assemble_build -> publish_release`

其语义是：

1. 从输入目录扫描文档。
2. 解析文档并切成 `raw_segment`。
3. 对 segment 做 enrich，补齐实体、语义角色等理解信息。
4. 为 segment 构建结构关系与部分扩展关系。
5. 以 segment 为基础生成检索单元 `asset_retrieval_units`。
6. 把本轮 snapshot 纳入 build。
7. 通过 release 激活当前 build，供 Serving 读取。

### 3.2 Serving 侧消费链路

当前 Serving 的 `/search` 主链在 `agent_serving/serving/api/search.py` 中已经落地为：

`normalize -> plan -> resolve_active_scope -> retrieve -> fuse -> rerank -> assemble`

其语义是：

1. 先理解用户 query。
2. 形成 `QueryPlan`。
3. 找到当前 channel 下唯一 active release 对应的 build。
4. 读取这个 build 下被选中的 snapshots。
5. 在这些 snapshots 的 `retrieval_units` 上做检索。
6. 对候选结果做融合、重排、去重。
7. 通过 source bridge 回到 `raw_segments` 和 relations，拼装成 `ContextPack`。

---

## 4. Mining 当前完成了什么

## 4.1 Mining 已经正式生产 retrieval units

当前 `knowledge_mining/mining/retrieval_units/__init__.py` 实际已经生产以下检索单元：

- `raw_text`
- `contextual_text`
- `entity_card`
- `generated_question`
- `table_row`

此外还存在一个基于 LLM contextual retrieval 的增强分支，但目前仍然写成 `unit_type="contextual_text"`，没有引入新的 unit type。

### 4.2 各类 retrieval unit 的职责

#### `raw_text`

- 与单个 `raw_segment` 基本一一对应。
- 保留原始正文，适合精确命中。
- 是最直接、最稳定的检索载体。

#### `contextual_text`

- 以 segment 为核心，在文本前面补 section path 或结构化上下文。
- 目标是提升“带上下文的 lexical 检索”效果。
- Serving 当前会把它与 `raw_text` 视为同源候选，做去重压制。

#### `entity_card`

- 从 `entity_refs_json` 派生出的实体检索单元。
- 把实体名、实体类型、局部上下文组织为独立检索文本。
- 目标是让“查某个命令/网元/参数”时更容易召回。

#### `generated_question`

- 由 `LlmQuestionGenerator` 通过 `llm_service` 生成。
- 本质是“这个 segment 能回答哪些问题”的问题式检索入口。
- 这说明当前 Mining 已经不只是 rule-based 文本拼接，而是已把 LLM 接到了 retrieval unit 生产链路里。

#### `table_row`

- 从表格型 segment 中进一步拆出的行级检索单元。
- 目标是提升参数表、映射表、配置表的细粒度召回能力。

### 4.3 Mining 已经补出的关键字段

当前每条 retrieval unit 除了 `text` / `search_text` 外，还会带上这些关键元数据：

- `unit_type`
- `target_type`
- `target_ref_json`
- `block_type`
- `semantic_role`
- `facets_json`
- `entity_refs_json`
- `source_refs_json`
- `llm_result_refs_json`
- `source_segment_id`

这几个字段中，协同最关键的是：

#### `source_segment_id`

- 当前已成为 Mining -> Serving 的强桥接字段。
- 它把 retrieval unit 直接指回产出它的 `asset_raw_segments.id`。
- Serving 的 source drill-down 当前优先使用它。

#### `search_text`

- 当前已经由 Mining 预处理后写入，用于 Serving 的 FTS5/BM25 查询。
- 它是中文检索可用性的核心准备层之一。

#### `source_refs_json`

- 它承载 provenance 溯源信息。
- 按协同设计，它本应成为可扩展来源链。
- 但当前 Mining 的 `_build_source_refs()` 只稳定写了：
  - `document_key`
  - `segment_index`
  - `offsets`
- 也就是说，当前它仍然偏弱，尚未完全承担 Serving 期望中的统一 provenance 合同。

#### `target_ref_json`

- 用来表达“这个 retrieval unit 的目标对象是什么”。
- 对 `raw_text/contextual_text` 来说通常还是 segment。
- 对 `entity_card` 则是 entity 目标。
- 这使得 Serving 在没有强桥接时仍有 fallback 路径。

---

## 5. Serving 当前是如何使用这些检索单元的

## 5.1 Serving 不是直接搜 raw_segment，而是先搜 retrieval_unit

当前 Serving 的正式读取链路是：

`active release -> build -> selected snapshots -> asset_retrieval_units`

这意味着 Serving 首先检索的是 `asset_retrieval_units`，而不是直接扫 `asset_raw_segments`。

这样做的好处是：

- 检索层可以承载多种表达视图，而不被原始段落形式绑死。
- 同一个 segment 可以产出多个检索入口。
- 后续 summary / community / entity aggregation 等更高阶载体也能复用同一 serving 主链。

## 5.2 Serving 如何限定检索范围

Serving 在 `resolve_active_scope()` 后会先得到：

- `release_id`
- `build_id`
- `snapshot_ids`
- `document_snapshot_map`

这一步的意义是：

- 只允许在当前 active build 选中的 snapshot 上做检索。
- 防止旧 build、非 active release 或其它 snapshot 的内容混进结果。

因此，Mining 发布了什么 build，Serving 才能读到什么 snapshot 范围。

## 5.3 Serving 如何检索 retrieval units

当前主 retriever 是 `FTS5BM25Retriever`。

它的特征是：

- 基于 `asset_retrieval_units_fts` 做 FTS5 检索。
- 查询词采用 OR 语义，而不是 phrase query。
- 对中文 query 先做 jieba 分词。
- 候选结果会带回：
  - `unit_type`
  - `source_segment_id`
  - `source_refs_json`
  - `target_ref_json`
  - `block_type`
  - `semantic_role`
  - `facets_json`

这意味着 Serving 的候选结果从一开始就不是“只有 text 的文本块”，而是已经带着协同用的桥接元数据。

## 5.4 Serving 如何重排这些候选

当前 reranker 会对 retrieval unit 候选做几类处理：

### 同源去重

若两个候选都来自同一个 `source_segment_id`，且 `unit_type` 属于：

- `raw_text`
- `contextual_text`

则只保留分数更高的一个。

这说明 Serving 已经明确接受一个事实：

- 一个 segment 可以有多个 retrieval view。
- 但返回给上层 Agent 时，不应让同源文本冗余淹没结果。

### 低价值块降权

当前会对 `heading / toc / link` 一类低价值块做降权。

### 规则加分

当前还会依据以下因素补分：

- intent 与 `semantic_role` 的匹配
- scope 与 facets 的匹配
- query entities 与 entity_refs 的匹配

这一步说明，Serving 对 retrieval unit 的使用已经不只是“查到即返回”，而是在做一层 retrieval-view-aware 的结果编排。

---

## 6. Mining 与 Serving 当前真正对齐的合同

## 6.1 当前最核心的合同：`source_segment_id`

这是当前两边最稳的合同。

协同方式是：

1. Mining 在生成 retrieval unit 时写出 `source_segment_id`。
2. Serving 检索到 retrieval unit 后，优先用 `source_segment_id` 回查原始 segment。
3. 回查出的 segment 再进入：
   - source item 组装
   - graph expansion
   - relations 输出
   - sources attribution

它的价值是：

- 语义清楚
- 查询简单
- 不依赖 JSON 结构解析
- 对 summary / question / entity_card 之类非 1:1 文本载体也成立

因此，从当前实现看，`source_segment_id` 已经是 Mining / Serving 的第一主合同。

## 6.2 第二层合同：`source_refs_json`

按协同设计，它应该是“可扩展 provenance 层”。

Serving 当前也已经按这个预期写了 fallback 逻辑，优先尝试解析其中的 `raw_segment_ids`。

但现实是：

- Serving 已经准备按它工作
- Mining 当前写出的 `source_refs_json` 还比较弱

因此这一层合同是“接口位已经对齐，但生产侧内容还没有完全做强”。

## 6.3 第三层合同：`target_ref_json`

这是当前的结构化 fallback。

它主要承担两类场景：

- retrieval unit 没有直接 segment bridge 时，仍能通过 target 回推
- 像 `entity_card` 这类不一定天然是一段原文的载体，仍能保留对象语义

Serving 在 assembler 中已经把它作为第三优先级使用。

## 6.4 Build / Release 合同

除了 unit 级合同，Mining / Serving 还有一层更上游的运行时合同：

- Mining 决定哪些 snapshot 被放进 build
- Serving 只读 active release 对应 build 的 snapshots

所以从系统层面说：

- `source_segment_id` 解决的是“怎么从检索单元回到内容片段”
- `build/release` 解决的是“Serving 当前允许看到哪一批内容”

这两层合同缺一不可。

---

## 7. 当前 Query Plan 处在什么阶段

## 7.1 QueryPlan 结构已经比较完整

当前 Serving 的 `QueryPlan` 已经不是一个轻量包装，而是正式执行计划对象，包含：

- `intent`
- `keywords`
- `entity_constraints`
- `scope_constraints`
- `desired_roles`
- `desired_block_types`
- `budget`
- `expansion`
- `retriever_config`
- `reranker_config`

这说明 Serving 的设计方向已经明确是 pipeline 化、可插拔化，而不是把检索策略写死在 API 层。

## 7.2 但 `/search` 当前主链仍主要走规则版 plan

虽然代码里已经有：

- `QueryNormalizer.anormalize()`
- `LLMPlannerProvider.abuild_plan()`

但 `/search` 当前实际调用的是：

- `QueryNormalizer().normalize()`
- `QueryPlanner(RulePlannerProvider()).plan()`

这意味着：

- plan 结构已经为 LLM planner 预留好了
- planner provider 代码也已经存在
- 但主请求链路还没有真正切到 LLM-first 的 plan 路径

因此当前应理解为：

- QueryPlan 合同已成型
- Serving 执行骨架已成型
- 但主链仍是 rule planner 主导，LLM planner 还没有完全进入正式执行入口

---

## 8. 当前协同方式的真实价值

## 8.1 为什么不是直接用 raw_segment 检索

因为 raw segment 是内容存储视图，不一定是最适合检索的视图。

同一个 segment 可以派生出多种检索入口：

- 原文精确匹配
- 带上下文匹配
- 实体聚合匹配
- 问题式匹配
- 表格行级匹配

Mining 负责生产这些检索入口，Serving 负责消费并编排它们，这样两边职责更清楚。

## 8.2 为什么 Serving 还要回到 raw_segment

因为 Agent 最终需要的不是“命中了一条 FTS 文本”，而是：

- 能追溯原始来源
- 能拿到相邻上下文
- 能展开 relations
- 能看到文档归属与 source 信息

所以 retrieval unit 只是入口视图，raw segment 才是内容真相源。

## 8.3 为什么 build/release 很关键

如果没有 build/release 约束，Serving 可能会把：

- 历史 snapshot
- 已退役 release
- 其它 build 的旧版本内容

混进当前查询结果。

当前 Mining / Serving 已经通过 active release -> build -> snapshot_ids 把这个问题收住了。

---

## 9. 当前还没有完全收口的地方

## 9.1 `source_refs_json` 仍偏弱

Serving 已经把它作为正式 fallback 合同在用，但 Mining 当前没有把它生产成足够强的统一 provenance 结构。

当前状态更像：

- 强桥接靠 `source_segment_id`
- JSON provenance 仍是半完成态

## 9.2 QueryPlan 的 LLM 主链接入还没彻底打通

结构和 provider 已经存在，但 `/search` 实际主链还在走 rule path。

## 9.3 Retrieval unit 类型仍在继续演进

当前 schema 已支持：

- `raw_text`
- `contextual_text`
- `summary`
- `generated_question`
- `entity_card`
- `table_row`

但生产侧与消费侧当前真正稳定跑通的主战场，还是：

- `raw_text`
- `contextual_text`
- `entity_card`
- `generated_question`

`summary` 目前还是 schema-ready、实现未全面落地的状态。

---

## 10. 最终结论

当前 Mining 和 Serving 围绕“检索单元”的协同，已经形成了一个可运行的正式主链：

1. Mining 把文档切成 `raw_segment`。
2. Mining 基于 segment 生产多种 `retrieval_unit`，并写出 `source_segment_id`。
3. Mining 通过 build/release 决定哪些 snapshots 对外生效。
4. Serving 在 active build 范围内检索 `retrieval_unit`。
5. Serving 通过 `source_segment_id -> source_refs_json -> target_ref_json` 回到 `raw_segment`。
6. Serving 再利用 relations 和 source attribution，最终组装成 `ContextPack` 返回给 Agent。

因此，当前两边协同的真正核心不是“同看一批文档”，而是：

- Mining 负责生产“检索视图”
- Serving 负责消费“检索视图”并回到“内容真相源”

如果用一句更准确的话来描述当前系统：

> Mining 负责把知识内容编译成可检索载体，Serving 负责把这些检索载体重新还原为可供 Agent 使用的上下文包。

