# TASK-20260421-v11-agent-serving Codex Review

## 审查背景

- 任务：`TASK-20260421-v11-agent-serving`
- 审查对象：Claude Serving 提交的 v1.1 `agent_serving/` 重写实现、对应 plan/handoff、与 `asset_core` / `agent_llm_runtime` 正式架构边界的一致性
- 审查基线：
  - `docs/architecture/2026-04-21-coremasterkb-v1.1-architecture.md`
  - `docs/plans/2026-04-21-v11-agent-serving-rewrite-plan.md`
  - `docs/handoffs/2026-04-21-v11-agent-serving-claude-serving-handoff.md`
  - `databases/asset_core/schemas/001_asset_core.sqlite.sql`
  - 提交链：`f4438eb` 到 `ecdcd7b`

## 审查范围

- `agent_serving/serving/` 主链：API / application / retrieval / repositories / schemas / tests
- `agent_serving/README.md`
- Serving plan、handoff 与最终代码的一致性

## 发现的问题

### P1. 检索主链仍然绑定单路 BM25，没有形成多路召回 / 融合 / 重排的正式 pipeline，当前实现不具备后续演进扩展性

- plan 明确把 v1.1 之后的演进路径定义为 `Retriever -> Fusion(RRF) -> Reranker -> Assembler`，并要求 QueryPlan 作为统一执行抽象承接多路召回、LLM rewrite、rerank policy 等后续能力。
- 实现中 `/search` 直接实例化 `FTS5BM25Retriever`，然后把候选列表直接交给 assembler；没有 `RetrieverManager`、没有 fusion 层、没有独立 reranker 层。
- `bm25_retriever.py` 里的 `_apply_post_filters()` 还把 role/block_type 偏好排序和最终截断直接写在 retriever 内部，召回和后排耦合在一起。后续无论是 vector recall、graph recall、LLM rerank 还是 cross-encoder rerank，都需要返工主链而不是插拔模块。
- 这意味着当前实现只是“单路 lexical retrieval 闭环”，不是“支持多路召回和多种重排的 Serving 底座”。
- 代码位置：
  - `agent_serving/serving/api/search.py:31-32`
  - `agent_serving/serving/api/search.py:61-106`
  - `agent_serving/serving/retrieval/retriever.py:13-31`
  - `agent_serving/serving/retrieval/bm25_retriever.py:62-127`
  - `agent_serving/serving/retrieval/bm25_retriever.py:193-226`
- 文档位置：
  - `docs/plans/2026-04-21-v11-agent-serving-rewrite-plan.md:192-205`
  - `docs/plans/2026-04-21-v11-agent-serving-rewrite-plan.md:243-245`
  - `docs/plans/2026-04-21-v11-agent-serving-rewrite-plan.md:458`

### P1. `QueryPlan` 和 `LLM` 接缝没有真正成立，Serving 还不是“rule-based default + LLM-backed provider”的可插拔结构

- plan 和 README 都把 Serving 的演进方向定义成 `Normalizer / QueryPlanner / LLM Runtime client / Reranker` 的可插拔链，但当前实现里并不存在真正的 `QueryPlanner`。
- `search.py` 直接在路由里 `_build_plan()`，只是把 `NormalizedQuery` 轻量包装成 `QueryPlan`；`application/planner.py` 实际上不是 planner，而是一个 placeholder `LLMRuntimeClient`。
- 更关键的是，这个 placeholder 还把职责写成“through agent_llm_runtime DB”，与正式架构要求的“通过独立 LLM service/client 接入，不直接依赖 runtime DB 细节”相冲突。
- `QueryNormalizer` 在 API 中也是裸实例化，未通过依赖注入接入任何统一 runtime client。当前并没有形成“规则默认 + LLM 可选 provider”的正式双层结构。
- 这会导致后续 `claude-llm` 一旦收口 runtime 合同，Serving 不是替换 provider，而是要继续拆主链。
- 代码位置：
  - `agent_serving/serving/api/search.py:39-58`
  - `agent_serving/serving/api/search.py:68-77`
  - `agent_serving/serving/application/normalizer.py:80-105`
  - `agent_serving/serving/application/planner.py:1-43`
- 架构位置：
  - `docs/architecture/2026-04-21-coremasterkb-v1.1-architecture.md:481-524`
- 文档位置：
  - `docs/plans/2026-04-21-v11-agent-serving-rewrite-plan.md:264-271`
  - `docs/plans/2026-04-21-v11-agent-serving-rewrite-plan.md:446-458`

### P1. `ActiveScope`、来源归属和图扩展没有严格受 build 视图约束，后续会把非 active 上下文混入 ContextPack

- `resolve_active_scope()` 在读取 `asset_build_document_snapshots` 时没有过滤 `selection_status='active'`，与 plan 明确要求的 build 选择语义不一致。
- `document_snapshot_map` 虽然被构造出来，但后续来源解析并没有真正使用这个 map；`get_document_sources()` 只是按 `document_id` 粗查 link / snapshot，无法保证来源一定属于当前 active build 选中的 snapshot。
- `GraphExpander.expand()` 也没有接收 `snapshot_ids` 或 build scope，只按 segment relation 做 BFS。多 snapshot 共存时，扩展出来的上下文可能越过 active build 边界。
- 这类问题在当前小测试库里不一定暴露，但一旦 Mining 开始输出 merge build、inactive selection、shared snapshot 等正式场景，Serving 会把错误上下文送进后续 rerank / LLM 阶段，风险会被放大。
- 代码位置：
  - `agent_serving/serving/repositories/asset_repo.py:55-72`
  - `agent_serving/serving/repositories/asset_repo.py:150-172`
  - `agent_serving/serving/application/assembler.py:141-148`
  - `agent_serving/serving/retrieval/graph_expander.py:23-77`
- 文档位置：
  - `docs/plans/2026-04-21-v11-agent-serving-rewrite-plan.md:100-103`
  - `docs/plans/2026-04-21-v11-agent-serving-rewrite-plan.md:279-304`
  - `docs/architecture/2026-04-21-coremasterkb-v1.1-architecture.md:316-327`

### P2. `source_refs_json` 只实现了最窄的 `raw_segment_ids` 路径，没有按 plan 交付 fallback 语义，未来兼容性不足

- plan 明确要求 `resolve_source_segments()` 的优先级是：
  1. `source_refs_json.raw_segment_ids`
  2. `target_type / target_ref_json`
  3. 都没有时再做低置信度 snapshot 级 fallback
- 当前实现只支持第一种。`AssetRepository._parse_segment_ids()` 和 `parse_source_refs()` 都只认 `raw_segment_ids`，其余情况直接返回空列表。
- 这会让后续 `generated_question`、summary、entity_card 等更复杂 retrieval unit 类型在 source_refs 缺字段、格式变化或仅有 target_ref 的情况下直接失去下钻与扩展能力。
- 代码位置：
  - `agent_serving/serving/repositories/asset_repo.py:81-116`
  - `agent_serving/serving/repositories/asset_repo.py:175-185`
  - `agent_serving/serving/retrieval/graph_expander.py:162-175`
- 文档位置：
  - `docs/plans/2026-04-21-v11-agent-serving-rewrite-plan.md:123-131`
  - `docs/plans/2026-04-21-v11-agent-serving-rewrite-plan.md:541`

## 测试缺口

- 当前没有覆盖多路召回 / fusion / rerank 的测试，因为对应执行层本身未实现。
- 当前没有覆盖 `selection_status != active` 的 build 选择测试；`resolve_active_scope()` 只在全 active seed 数据上验证。
- 当前没有覆盖 graph expansion 必须限制在 active snapshot/build 内的测试。
- 当前没有覆盖 `target_ref_json` fallback 或 source_refs 结构变化时的 drill-down 测试。
- `test_mining_contract.py` 仍是跳过占位，无法证明与正式 Mining v1.1 输出的真实兼容性。

## 回归风险

- 如果继续在当前主链上叠加 vector recall、RRF、rerank，会把 API、retriever、assembler 一起牵动，演进成本高且容易引入行为回归。
- 如果 `claude-llm` 定稿后再接统一 runtime，当前“伪 planner + placeholder client”路径会造成第二轮主链拆分。
- 如果 Mining 输出 inactive selection、shared snapshot、merge build，当前 Serving 有较高概率把非 active 内容混入 ContextPack。
- 如果 retrieval unit 类型从 `raw_text/contextual_text` 扩展到 `generated_question/summary/entity_card`，当前 source drill-down 兼容性会直接掉档。

## 建议修复项

1. 先把 `/search` 主链重构成正式可插拔 pipeline：
   - `Normalizer`
   - `QueryPlanner`
   - `RetrieverManager`
   - `Fusion`
   - `Reranker`
   - `Assembler`
2. 即使 v1.1 仍只启用 BM25，也要让 BM25 走统一 `RetrieverManager -> Fusion -> Reranker` 空实现链，不要继续在 API 中绑定单路 retriever。
3. 把 `QueryPlan` 升级成稳定执行合同，至少能承接 retriever selection、rerank policy、expansion policy、future multi-query 等字段。
4. `LLM` 这轮不要求先接通，但必须把 Serving 侧的 `LLMNormalizerProvider / LLMPlannerProvider / LLMRerankerProvider` 接缝立住，并明确后续只能通过 `claude-llm` 收口后的统一 runtime client 接入。
5. 修正 build 视图一致性：
   - `resolve_active_scope()` 过滤 `selection_status='active'`
   - 来源归属真正使用 `document_snapshot_map`
   - graph expansion 增加 active snapshot/build 约束
6. 按 plan 补齐 `source_refs_json -> target_ref_json -> snapshot fallback` 的分层解析与测试。

## 无法确认的残余风险

- 当前未复跑 `agent_serving/tests`，本轮结论主要基于最终代码、plan、handoff 和测试内容静态审查。
- 因 `test_mining_contract.py` 仍为 skipped，占位测试无法证明与真实 Mining v1.1 输出的兼容性。
- `claude-llm` 正在继续修 runtime 合同，因此本次 review 没把“LLM 具体调用实现缺失”作为 Serving 本轮必须闭环项，而是聚焦于可插拔 pipeline 接缝是否已准备好。

## 管理员介入影响

- 用户已明确要求本轮审查按“可演进到多路召回、多重排、统一 LLM pipeline”的标准判断，而不是只看当前单路 BM25 是否可运行。
- 用户同时明确：`claude-llm` 仍在收口统一合同，因此 Serving 当前重点不是私自补完 LLM 逻辑，而是把可插拔 pipeline 骨架先立稳。

## 最终评估

- 当前实现已经站上了正确的 1.1 架构主线：不再依赖旧 command/canonical 结构，主输出也已切到 `ContextPack`。
- 但它还只是“单路 lexical retrieval + graph context”的最小闭环，不是“支持多路召回、多种重排、统一 LLM pipeline 接入”的稳定底座。
- 结论：**存在需要 Claude Serving 修复的实质问题。当前不建议把 handoff 所述实现视为 Serving v1.1 的可扩展闭环版本。**
