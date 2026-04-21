# v1.1 Agent Serving 重写方案

- 日期：2026-04-21
- 作者：Claude-Serving
- 状态：v2 — 对齐 Mining v3 plan 后修订
- 关联任务：TASK-20260421-v11-agent-serving
- 关联消息：MSG-20260421-101600-codex

---

## 0. 整体目标

围绕 `retrieval_units` + `raw_segment_relations` + `ContextPack`，把在线知识服务重写成 Agent 可消费的通用检索后台。

**全部重写，不依赖任何现有实现。**

### 确认的设计决策

| # | 决策 | 选择 |
|---|---|---|
| 1 | 检索范围 | 严格限定 active release → build → document_snapshot_pairs |
| 2 | Active 缓存 | 每次请求实时查 DB |
| 3 | source_refs_json | **解析进入正式读取逻辑**，用于内容级下钻和证据锚定 |
| 4 | Relations | 独立一等结构 list[ContextRelation] |
| 5 | Normalizer | LLM Runtime client + 规则 fallback |
| 6 | 检索架构 | Retriever 接口 + FTS5BM25Retriever + GraphExpander + RRF 预留 |
| 7 | 中文分词 | 应用层 jieba |
| 8 | 测试数据 | 内存 SQLite + conftest seed，contract tests 等 Mining 产出后补 |
| 9 | QueryPlan | 统一执行语义，不管来源是规则/LLM/未来 planner |

### 保留的代码

- `main.py`（FastAPI 骨架，改版本号）
- `api/health.py`（健康检查）
- `repositories/schema_adapter.py`（读共享 DDL）
- `tests/test_health.py`、`test_schema_adapter.py`、`test_install_smoke.py`

其余全部删除重写。

---

## 1. 读取链路

Serving 的正式读取路径：

```
请求进来
  → 解析 active scope（release → build → document→snapshot 映射）
  → 校验：0 个 active → 503，多个 active → 500 数据完整性错误，1 个 → 正常
  → 在 snapshot_ids 范围内检索 retrieval_units
  → 解析 source_refs_json 获取每个 unit 引用的 raw_segment_ids（内容级下钻）
  → 从这些 segments 起跳做 GraphExpander（上下文扩展）
  → 解析 target_ref_json 作为补充信息（generated_question 回落到哪个 segment）
  → 解析 snapshot→document 映射（文档来源归属）
```

### 对齐 Mining v3 的 retrieval_unit 类型

Mining v1.1 会产出的 retrieval_unit 类型：

| unit_type | 含义 | 与 raw_segment 关系 | source_refs_json 内容 |
|---|---|---|---|
| raw_text | segment 原文精确匹配 | 1:1 | `{raw_segment_ids: ["seg-1"]}` |
| contextual_text | 带 section 上下文增强 | 1:1 | `{raw_segment_ids: ["seg-1"]}` |
| generated_question | LLM 生成的查询问题 | 1:1 或 N:1 | `{raw_segment_ids: ["seg-1"]}` |

v1.2 会追加：

| unit_type | 含义 | 与 raw_segment 关系 | source_refs_json 内容 |
|---|---|---|---|
| summary | section/document 级摘要 | N:1（聚合多个 segment） | `{raw_segment_ids: ["seg-1","seg-2","seg-3"]}` |
| entity_card | 跨 segment 实体聚合 | N:N | `{raw_segment_ids: ["seg-5","seg-12","seg-30"]}` |

**关键结论**：retrieval_unit 从来不是 snapshot 级薄封装。Serving 必须通过 source_refs_json 精确知道每个 unit 引用了哪些 raw_segments，否则会退化为"按 snapshot 模糊猜"。

---

## 2. ActiveScope 设计

### 不能只退化成 snapshot_ids 集合

build 的语义是：当前知识视图中，每个 document 采用哪个 snapshot。

ActiveScope 必须至少包含：

- `release_id`：当前 active release
- `build_id`：对应的 build
- `snapshot_ids`：build 选中的 snapshot 集合（用于检索范围控制）
- `document_snapshot_map`：document_id → snapshot_id 的映射（用于文档归属和来源解析）

### 为什么需要 document_snapshot_map

1. **文档来源归属**：一个 item 命中的 retrieval_unit 属于哪个 document？通过 snapshot_id 反查 document
2. **共享 snapshot 场景**：一个 snapshot 可以被多个 document 复用（相同内容），需要知道具体是哪个 document
3. **个性化视图扩展**：后续 build 级别的过滤/boosting 需要知道 document 粒度

### resolve_active_scope 的具体逻辑

1. 查 `asset_publish_releases WHERE status = 'active'`，校验 count == 1
2. 拿 build_id，查 `asset_build_document_snapshots WHERE build_id = ? AND selection_status = 'active'`
3. 从结果构建：
   - `snapshot_ids = {row.document_snapshot_id for row in rows}`
   - `document_snapshot_map = {row.document_id: row.document_snapshot_id for row in rows}`

---

## 3. source_refs_json 进入正式读取逻辑

### 三层引用关系

```
document_snapshot_id  → 用于范围控制（哪些 retrieval_units 在 scope 内）
source_refs_json      → 用于内容级下钻（这个 unit 引用了哪些 raw_segments）
target_ref_json       → 补充信息（generated_question 指向哪个 segment）
```

### resolve_source_segments(unit_ids) — 替代旧的粗 JOIN

这个方法的核心语义：**从 retrieval_unit 精确解析出它引用的 raw_segments**。

优先级规则：

1. **优先使用 source_refs_json.raw_segment_ids**：解析 JSON，取出 segment_id 列表，精确查询这些 segments
2. **若没有 source_refs_json 或解析失败**：看 target_type / target_ref_json，尝试提取 segment_id
3. **如果都没有**：退化成 snapshot 级补充（按 document_snapshot_id 取相关 segments，但必须标记为低置信度来源）

这个方法取代旧方案中"按 snapshot 粗 JOIN 全部 segments"的做法。

### GraphExpander 的 seed 来源必须从这里来

GraphExpander 的输入 segment_ids 不能凭空产生，必须按上面的优先级规则从 source_refs_json 解出。否则：
- generated_question 命中后，不知道应该从哪个 segment 起跳做上下文扩展
- summary 命中后，不知道它聚合了哪些 segments
- 会退化为"从整个 snapshot 里随便挑 segment"

---

## 4. 模型设计

### 请求：SearchRequest

- `query: str` — 用户原始查询
- `scope: dict | None` — 通用 facets
- `entities: list[EntityRef] | None` — 可选的实体约束
- `debug: bool = False`

### 中间模型

- **NormalizedQuery**：original_query / intent / entities / scope(dict) / keywords / desired_roles
- **QueryPlan**：统一执行语义。不管来源是规则 fallback、LLM rewrite、还是未来 planner 演进，最终都产出 QueryPlan。包含 keywords / entity_constraints / scope_constraints / desired_roles / desired_block_types / budget / expansion 配置
- **RetrievalBudget**：max_items=10 / max_expanded=20 / recall_multiplier=5
- **ExpansionConfig**：enable=True / max_depth=2 / relation_types

### 响应：ContextPack

- **query**: ContextQuery — 原始/归一化/意图/实体/关键词
- **items**: list[ContextItem] — seed(检索命中) + context(图扩展) 混合列表
- **relations**: list[ContextRelation] — 独立一等结构，from_id / to_id / relation_type / distance
- **sources**: list[SourceRef] — 文档级来源（去重后）。注意这只是来源索引，不是完整证据包
- **issues**: list[Issue] — no_result / low_confidence / ambiguous_scope / partial_context
- **suggestions**: list[str] — 建议跟进查询
- **debug**: dict | None — 可选调试信息

### sources 不替代完整证据包

文档去重后的 sources 保留，但它只是来源索引。真正的证据包是 items + relations + source_refs lineage + raw_segments / section / offsets 的完整组合。ContextPack 的消费者（Agent）应该综合所有字段理解证据，不能只看 sources。

### ContextItem 设计

- `kind`: retrieval_unit / raw_segment
- `role`: seed(检索命中) / context(图扩展) / support(辅助)
- `relation_to_seed`: context items 才有
- `source_id`: 指向 sources 列表中的文档
- `source_refs`: 透传原始 source_refs_json，供 Agent 深入追溯

### Intent 类型

command_usage / troubleshooting / concept_lookup / procedure / general

---

## 5. 检索架构

### 整体管线

```
SearchRequest
  ↓
QueryNormalizer (LLM + 规则 fallback)
  → NormalizedQuery
  ↓
QueryPlanner（统一执行语义）
  → QueryPlan（规则产出 / LLM rewrite 产出 / 未来 planner 产出，格式统一）
  ↓
Retriever 接口
  ├─ FTS5BM25Retriever（第一版实现）
  │   → jieba 分词 query → FTS5 MATCH + bm25() 评分
  │   → 无结果时 LIKE %keyword% 兜底
  │   → 限定 snapshot_ids 范围
  └─ (未来) VectorRetriever / HybridRetriever
  ↓
RRF Fusion（接口预留）
  ↓
resolve_source_segments(unit_ids)
  → 从 source_refs_json 解出 raw_segment_ids（内容级下钻）
  → 这些 segments 同时作为 GraphExpander 的 seed
  ↓
GraphExpander
  → 从 seed segments 起跳遍历 raw_segment_relations
  → 支持多跳（max_depth=2）和多类型混合
  ↓
ContextPackAssembler
  → 组装 seed + context + relations + sources + issues
  ↓
ContextPack 输出
```

### Retriever 接口

核心方法：`recall(plan, snapshot_ids) -> list[RetrievalCandidate]`

`RetrievalCandidate`：retrieval_unit_id / score / source(bm25/vector/graph) / metadata。

### FTS5BM25Retriever 核心逻辑

1. **query 分词**：jieba.cut_for_search(query) → 去停用词 → 拼成 FTS5 OR 表达式
2. **FTS5 检索**：`MATCH ?` + `bm25()` 评分 + 限定 snapshot 范围 + LIMIT recall_limit
3. **scope 过滤**（Python 侧）：按 facets_json 做 scope 交集检查，缺失字段不判死
4. **LIKE 兜底**：FTS 无结果时，对每个 keyword 做 `search_text LIKE ?`
5. **评分**：bm25 分数 + scope 匹配加分 + entity 匹配加分

### GraphExpander 核心逻辑

**seed 来源**（按优先级）：
1. source_refs_json.raw_segment_ids（精确）
2. target_type / target_ref_json（补充）
3. 都没有 → 不做 segment 级 graph expansion

**遍历方式**：SQL BFS，每跳一条 SQL，去重防循环，限制 max_depth=2。

**输出**：扩展的 raw_segments + relation_type + distance + 经过的路径。

### RRF Fusion

接口预留。第一版只有一个检索源，RRF 退化为直接排序。未来加 Vector 后只需传入多个列表和权重。

---

## 6. Normalizer 设计

### 双路径：LLM + 规则 fallback

- 有 LLM Runtime client 时：调用 LLM 做 intent/entity/scope/keyword 提取
- 无 LLM 或调用失败时：fallback 到规则提取

### 规则 fallback 逻辑

- **intent 检测**：关键词匹配
- **entity 提取**：正则匹配命令/产品名/网元名/版本号
- **scope 提取**：存为通用 dict
- **keyword 提取**：jieba 分词 + 去停用词
- **desired_roles**：根据 intent 映射偏好 semantic_role

### QueryPlan 是统一执行抽象

不管来源如何，最终都产出 QueryPlan：
- 规则 fallback → QueryPlan
- LLM rewrite → QueryPlan
- 未来 planner 演进 → QueryPlan

下游所有组件（Retriever / GraphExpander / Assembler）只消费 QueryPlan，不关心它的来源。

---

## 7. Repository 设计

### 核心方法

- **resolve_active_scope()** → ActiveScope(release_id, build_id, snapshot_ids, document_snapshot_map)
- **search_retrieval_units(plan, snapshot_ids)** → 调用 Retriever 接口，返回候选列表
- **resolve_source_segments(unit_ids)** → 从 source_refs_json 解出 raw_segment_ids，精确取 segments
- **expand_relations(segment_ids, relation_types, snapshot_ids)** → 调用 GraphExpander
- **resolve_sources(snapshot_ids, document_snapshot_map)** → snapshot → links → documents

### resolve_sources 的 JOIN 路径

```
document_snapshot_map
  → asset_document_snapshot_links (document_id + snapshot_id)
  → asset_documents (document_key / title)
```

不再只通过 snapshot_id 粗 JOIN，而是利用 build 选择的 document→snapshot 映射精确解析文档归属。

---

## 8. Assembler 设计

### 组装逻辑

1. **seed items**：从 retrieval_units 构造，kind=retrieval_unit, role=seed，附带 source_refs 原始数据
2. **context items**：从 GraphExpander 扩展的 raw_segments 构造，kind=raw_segment, role=context
3. **relations**：从 GraphExpander 遍历路径构造独立 ContextRelation 列表
4. **sources**：从 document_snapshot_map 精确解析文档归属，按 document 去重聚合
5. **issues**：检测 no_result / low_confidence / ambiguous_scope / partial_context
6. **suggestions**：根据 issues 生成建议

### JSON 容错

所有 JSON 字段统一走容错解析：None→默认值，str→json.loads 失败→默认值，已解析→原样。

---

## 9. API 设计

### 单一端点

`POST /api/v1/search` → ContextPack

### 请求流程

```
1. resolve_active_scope() → ActiveScope（含 document_snapshot_map）
2. QueryNormalizer.normalize() → NormalizedQuery
3. QueryPlanner.build_plan() → QueryPlan
4. Retriever.recall(plan, snapshot_ids) → 候选 retrieval_units
5. resolve_source_segments(unit_ids) → 精确 source segments（GraphExpander seed）
6. GraphExpander.expand(seed_segment_ids, relation_types) → 扩展 segments + relations
7. resolve_sources(snapshot_ids, document_snapshot_map) → 文档来源
8. Assembler.assemble() → ContextPack
9. debug 填充（可选）
```

### 错误处理

- 无 active release → HTTP 503
- 多个 active release → HTTP 500
- 查询无结果 → 正常返回 ContextPack，issues 含 no_result

---

## 10. 文件规划

```
agent_serving/serving/
├── main.py                    (保留，改版本号)
├── api/
│   ├── health.py              (保留不动)
│   └── search.py              (重写)
├── schemas/
│   ├── models.py              (重写 — ContextPack 全套模型)
│   └── constants.py           (重写)
├── application/
│   ├── normalizer.py          (重写 — LLM + 规则 fallback)
│   ├── normalizer_config.py   (重写)
│   ├── assembler.py           (重写 — ContextPackAssembler)
│   └── planner.py             (新增 — QueryPlan 统一构建)
├── retrieval/
│   ├── __init__.py            (新增)
│   ├── retriever.py           (新增 — Retriever 接口 + RRF)
│   ├── bm25_retriever.py      (新增 — FTS5 + jieba + LIKE fallback)
│   └── graph_expander.py      (新增 — relation 遍历)
├── repositories/
│   ├── asset_repo.py          (重写 — 面向新 schema + source_refs 解析)
│   └── schema_adapter.py      (保留不动)
└── llm/
    ├── __init__.py            (新增)
    └── client.py              (新增 — LLM Runtime client)

agent_serving/tests/
├── conftest.py                (重写 — v1.1 schema seed data)
├── test_health.py             (保留)
├── test_schema_adapter.py     (保留)
├── test_install_smoke.py      (保留)
├── test_models.py             (重写)
├── test_normalizer.py         (重写)
├── test_retriever.py          (新增 — BM25Retriever + GraphExpander)
├── test_asset_repo.py         (重写 — 含 source_refs 解析测试)
├── test_assembler.py          (重写)
├── test_api_integration.py    (重写)
└── test_mining_contract.py    (重写 — 等 Mining 产出后补)
```

---

## 11. 执行顺序

```
Task 1: 清空旧代码
Task 2: 定义模型 (schemas/)
Task 3: Retriever 架构 (retrieval/)
Task 4: 重写 Repository (repositories/ — 含 source_refs 解析)
Task 5: 重写 Normalizer + Planner (application/)
Task 6: 重写 Assembler (application/)
Task 7: 重写 API (api/)
Task 8: 重写测试 (tests/)
```

依赖关系：

```
Task 1 + Task 2 (并行)
  → Task 3 + Task 5 (并行，都只依赖 Task 2 的模型)
    → Task 4 (依赖 Task 3 的 Retriever)
      → Task 6 (依赖 Task 4)
        → Task 7 (依赖 Task 4 + 5 + 6)
          → Task 8 (依赖全部)
```

---

## 12. 工业级检索架构演进参考

> 本节是工业级演进方向的参考映射，不是当前版本的承诺。对齐 Mining v3 plan 的演进节奏，给出 Serving 每个阶段对应的检索能力变化。

### 12.1 检索方式演进

工业级做法（Elasticsearch / Milvus / Weaviate）：BM25 + Dense Vector 双通道检索，RRF 融合，支持多字段加权。

| 能力 | 我们的落点 | v1.1 | v1.2 | v1.3+ |
|-----|-----------|------|------|-------|
| 词汇检索 | FTS5BM25Retriever | jieba 分词 + FTS5 + LIKE 兜底 | 同左 | 同左 |
| 向量检索 | asset_retrieval_embeddings + VectorRetriever | 不做 | 接入 embedding 表，余弦相似度 | 外部向量库可选 |
| 混合检索 | HybridRetriever + RRF | 单通道退化 | BM25 + Vector RRF 融合 | 多通道 + 动态权重 |
| 分词增强 | search_text 字段 | 应用层 jieba | Mining 侧拼好分词结果到 search_text | 同左 |

### 12.2 图扩展演进

工业级做法（Microsoft GraphRAG / LlamaIndex）：从匹配实体出发，1-2 跳图遍历，收集关联文本 + 实体描述 + 社区摘要。

| 能力 | 我们的落点 | v1.1（结构关系） | v1.2（+语义关系） | v1.3（+实体图） |
|-----|-----------|----------------|-----------------|----------------|
| 结构扩展 | GraphExpander → raw_segment_relations | previous/next/same_section/section_header_of | 同左 | 同左 |
| 语义扩展 | GraphExpander → raw_segment_relations | 不做 | + references/elaborates/condition/contrast | 同左 |
| 实体图扩展 | 新表 asset_entity_relations | 不做 | 不做 | 实体→实体关系遍历 |
| 社区聚合 | 新表 asset_communities | 不做 | 不做 | Leiden 社区 → 上下文聚合 |
| 扩展策略 | ExpansionConfig | max_depth=2, 固定类型 | 按意图动态选关系类型 | 按社区相关性剪枝 |

### 12.3 查询理解演进

工业级做法（LangChain QueryTransform / LlamaIndex）：LLM 做 query rewrite / HyDE / step-back / multi-query，输出统一的检索计划。

| 能力 | 我们的落点 | v1.1 | v1.2 | v1.3+ |
|-----|-----------|------|------|-------|
| 规则理解 | RuleBasedFallback | 正则 + 关键词 | 同左 | 同左（兜底） |
| LLM intent | LLM Runtime client → NormalizedQuery | LLM 可用时调用 | 同左，prompt 优化 | 同左 |
| Query rewrite | QueryNormalizer | 不做 | LLM 改写查询扩展召回 | HyDE / multi-query |
| Retrieval planning | QueryPlanner | 静态 plan 构建 | LLM 辅助选检索策略 | 完整 retrieval planner |
| Multi-query | QueryPlan 扩展 | 不做 | 不做 | 一个 query 拆多个子 query 并行检索 |

### 12.4 重排与压缩演进

工业级做法（Cohere Rerank / BGE-Reranker / LLM compression）：检索后重排提升精度，压缩上下文降低 token 消耗。

| 能力 | 我们的落点 | v1.1 | v1.2 | v1.3+ |
|-----|-----------|------|------|-------|
| 粗排 | Retriever 评分 | bm25 + scope/entity 加分 | 同左 | 同左 |
| 重排 | Reranker 接口预留 | 不做 | LLM rerank（调用 LLM Runtime） | Cross-encoder 模型 |
| 上下文压缩 | Assembler 截断 | budget.max_items 硬截断 | LLM 压缩冗余上下文 | 摘要级压缩 |

### 12.5 ContextPack 输出演进

工业级做法（GraphRAG Local/Global/DRIFT）：根据查询类型返回不同粒度的上下文包。

| 查询类型 | v1.1 返回 | v1.2 返回 | v1.3 返回 |
|---------|----------|----------|----------|
| 具体问题（命令/参数） | seed retrieval_units + segment 上下文 | + summary 补充 | + entity_card 聚合 |
| 概念解释 | seed + same_section 扩展 | + summary 替代长段 | + 社区摘要 |
| 宏观总结 | 当前能力有限（多 seed 聚合） | summary retrieval_unit 直接命中 | 社区报告级别输出 |
| 跨文档关联 | 单 snapshot 内扩展 | + 语义关系跨文档 | + 实体图跨文档 |

### 12.6 证据溯源演进

工业级做法（GraphRAG citation / RAGAS faithfulness）：每个输出 item 都能追溯到原始文本位置。

| 能力 | 我们的落点 | v1.1 | v1.2 | v1.3 |
|-----|-----------|------|------|------|
| 文档级溯源 | SourceRef | document_key + title | 同左 | 同左 |
| 段落级溯源 | ContextItem.source_refs | source_refs_json 透传 | 同左 | 同左 |
| 行号级定位 | SourceRef.source_offsets | source_offsets_json | 同左 | 同左 |
| 实体级溯源 | 新表 asset_entities | 不做 | 不做 | 实体 → 出现过的所有 segments |

### 12.7 演进路线汇总

```
v1.1（当前版本）
├── FTS5 + jieba 词汇检索 + LIKE 兜底
├── GraphExpander：结构关系（previous/next/same_section/section_header_of）
├── resolve_source_segments：source_refs_json 内容级下钻
├── QueryNormalizer：LLM + 规则 fallback
├── QueryPlan：统一执行抽象
├── Retriever 接口：可替换检索后端
├── RRF Fusion：接口预留
├── ContextPack：seed + context + relations + sources
└── ActiveScope：含 document_snapshot_map

v1.2（对齐 Mining v1.2，零表变更）
├── VectorRetriever：接入 asset_retrieval_embeddings
├── HybridRetriever：BM25 + Vector RRF 融合
├── GraphExpander：+语义关系（references/elaborates/condition/contrast）
├── LLM query rewrite：扩展召回面
├── LLM rerank：重排候选结果
├── summary / entity_card 消费：新 retrieval_unit 类型适配
└── 按意图动态选关系类型

v1.3（对齐 Mining v1.3，需新表）
├── 实体图扩展：asset_entity_relations 遍历
├── 社区聚合：asset_communities + asset_community_reports
├── 完整 retrieval planner（LLM 驱动）
├── Multi-query 拆分并行检索
├── 上下文压缩（LLM 压缩冗余）
├── 实体级溯源
└── 按查询类型返回不同粒度 ContextPack（Local/Global 模式）

v1.4+（持续演进，参考方向）
├── Cross-encoder rerank 模型
├── 个性化视图（用户级 build 过滤/boosting）
├── 多语言检索
├── 实时反馈学习（点击/采纳信号）
├── 外部向量库可选后端（Milvus/Weaviate）
└── GraphRAG DRIFT 模式（Local+Global 迭代）
```

### 12.8 表变更规划

| 版本 | Serving 是否需要新表 | 说明 |
|------|---------------------|------|
| v1.1 | 否 | 只读现有 asset_core 表，新增 retrieval/ 模块是纯代码 |
| v1.2 | 否 | 消费 Mining 新增的 retrieval_unit 类型（summary/entity_card），读已有 embedding 表 |
| v1.3 | 是（Mining 侧创建） | Serving 读取 asset_entities / asset_entity_relations / asset_communities / asset_community_reports |
| v1.4+ | 待定 | 外部向量库/个性化表 待评估 |

---

## 13. 前置条件和风险

1. **DDL 已就绪**：`databases/asset_core/schemas/001_asset_core.sqlite.sql` 已更新到 v1.1 新架构
2. **Mining 尚未产出新 schema DB**：contract tests 等 Mining 完成后补，第一版用 conftest seed data
3. **jieba 依赖**：需要 `pip install jieba`，纯 Python 包，无编译依赖
4. **LLM Runtime 尚未就绪**：Normalizer 的 LLM 路径先写 client 接口，依赖 claude-llm 完成
5. **source_refs_json 格式约定**：Serving 需要和 Mining 对齐 source_refs_json 的内部结构。当前约定是 `{raw_segment_ids: [...]}`，但需要容错解析（字段缺失或格式变化时 fallback）
6. **document_snapshot_map 复杂度**：build 选择的 document→snapshot 映射可能较大（数百文档），需要评估内存影响
