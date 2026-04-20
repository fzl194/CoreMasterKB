# Agent LLM Module Requirements Analysis

- 日期：2026-04-20
- 作者：Codex
- 类型：需求分析
- 关联背景：
  - `.dev/2026-04-20-agent-knowledge-backend-redesign.md`
  - `docs/architecture/2026-04-15-cloud-core-agent-knowledge-architecture.md`
  - `docs/architecture/2026-04-15-mining-serving-parallel-design.md`
  - `knowledge_assets/schemas/001_asset_core.sql`
  - `knowledge_assets/schemas/001_asset_core.sqlite.sql`

## 1. 背景

当前项目已经拆成 Knowledge Mining 和 Agent Serving 两条主线：

- Mining 负责离线生产知识资产。
- Serving 负责在线读取 active 资产并返回 Agent 可消费的 evidence/context。
- 两者通过 `knowledge_assets/schemas/` 中的数据库资产契约对接，不互相 import。

dev 最新笔记进一步提出：后续主路径应从 canonical 主导的归并检索，转向 raw segment + retrieval unit + relation 的通用 RAG/Graph RAG 方向，并预留 LLM planner、rerank、context compression 等能力。

用户本轮新增要求是：构建一个独立 Agent 模块，支撑 Claude Mining 和 Claude Serving 在各自 pipeline 中调用 LLM；该模块需要记录输入输出、自动解析 JSON、落盘到自己的数据表、有队列，并能通过字段区分 mining/serving，同时调用方传入挖掘或查询 ID，便于关联 LLM 结果。

## 2. 需求结论

需要新增的不是放在 Mining 或 Serving 里的工具函数，而是一个独立的 LLM Agent Runtime / LLM Task System。

建议命名为：

```text
agent_runtime
```

或更明确：

```text
llm_agent_runtime
```

它的定位是：

```text
Mining pipeline / Serving pipeline
  -> Agent LLM Runtime client
  -> queue + worker
  -> LLM provider
  -> response parser
  -> runtime-owned tables
  -> result lookup by task/run/ref id
```

这个模块应独立于 `knowledge_mining/**` 和 `agent_serving/**`，但可以被两边调用。它不能反向 import Mining/Serving 的业务实现。

## 3. 设计目标

### 3.1 必须支持

1. **统一 LLM 调用入口**
   - Mining 和 Serving 都通过同一套 client API 发起 LLM 任务。
   - 不允许两边各自直接封装 provider，避免日志、重试、JSON 解析、成本统计分裂。

2. **输入输出完整记录**
   - 保存调用请求、prompt/messages、model、provider、参数、输入引用、原始响应、解析结果、错误信息、token/cost/latency。
   - 保存足够审计信息，但敏感字段如 API key 不能落库。

3. **自动 JSON 解析**
   - 支持调用方声明 `expected_output = json/object/array/text`。
   - 支持 JSON schema 或 Pydantic schema 名称。
   - 保存三份结果：
     - `raw_output_text`
     - `parsed_output_json`
     - `parse_status / parse_error`
   - 解析失败不能吞掉原始输出。

4. **独立数据表**
   - 不写入 `asset_*` 表。
   - 不写入 Mining/Serving 私有业务表。
   - Runtime 自己拥有任务、尝试、消息、结果表。

5. **队列**
   - 调用方可以提交异步任务。
   - Worker 从队列表中 claim 任务、执行、重试、落结果。
   - M1 可以先用 SQLite 表轮询队列，不需要 Redis/Celery。

6. **区分 mining / serving**
   - 每条任务必须有 `caller_domain` 字段，取值至少：
     - `mining`
     - `serving`
   - 后续可扩展 `evaluation`、`admin`、`offline_repair`。

7. **传入业务关联 ID**
   - Mining 调用时必须传入挖掘侧关联 ID，例如：
     - `publish_version_id`
     - `source_batch_id`
     - `raw_document_id`
     - `raw_segment_id`
     - `retrieval_unit_id`
     - `mining_job_id`
   - Serving 调用时必须传入查询侧关联 ID，例如：
     - `request_id`
     - `query_id`
     - `context_pack_id`
     - `session_id`
     - `retrieval_trace_id`
   - 不建议只做一个 `related_id`，应使用 `caller_domain + pipeline_stage + ref_type + ref_id`，避免 ID 语义混乱。

## 4. 非目标

第一版不应做：

- 不做通用多 Agent 框架。
- 不做复杂 workflow DSL。
- 不替代 Mining pipeline 编排。
- 不替代 Serving QueryPlan / retriever / assembler。
- 不直接写 `asset_raw_segments`、`asset_canonical_segments` 或未来 `asset_retrieval_units`。
- 不把 LLM 输出默认为事实源；LLM 输出必须带 provenance、schema、解析状态和审核/置信信息。
- 不要求第一版接入多个外部 provider；可以先设计 Provider 接口，默认实现一个 mock/provider stub。

## 5. 模块边界

建议目录：

```text
agent_runtime/
  __init__.py
  runtime/
    client.py
    queue.py
    worker.py
    providers.py
    parser.py
    schemas.py
    repositories.py
    config.py
  scripts/
    run_worker.py
  tests/
```

边界规则：

| 方向 | 允许 |
|---|---|
| `knowledge_mining` -> `agent_runtime` | 允许，提交 LLM 任务、查询结果 |
| `agent_serving` -> `agent_runtime` | 允许，提交 LLM 任务、同步/异步获取结果 |
| `agent_runtime` -> `knowledge_mining` | 禁止 |
| `agent_runtime` -> `agent_serving` | 禁止 |
| `agent_runtime` -> `knowledge_assets.schemas` | 可读共享 runtime DDL 或由 `scripts/init_db.py` 统一初始化 |

## 6. 调用场景

### 6.1 Mining 场景

Mining 可用 LLM 做离线增强，但不能让 LLM 改写事实源。

适合场景：

| 场景 | 输入 | 输出 | 写回策略 |
|---|---|---|---|
| segment 语义角色增强 | raw segment + section_path | semantic_role 候选 | 人工/规则确认后再进入 asset 字段，或先进入 runtime result |
| 实体抽取增强 | raw segment/table/list | entity refs 候选 | 不直接覆盖规则抽取结果，记录来源 |
| retrieval unit 生成 | raw segment + context | contextual_text / generated_question | 可写入未来 retrieval_units，但必须保留 LLM task id |
| 章节摘要 | section segments | summary | 作为 retrieval unit 或 metadata，不作为原文事实 |
| 冲突摘要 | L2 candidate pair | diff_summary candidate | 标记为 generated，不自动当最终冲突结论 |

Mining 调用必须带：

```text
caller_domain = mining
pipeline_stage = segment_enrichment | entity_extraction | retrieval_unit_generation | summarization | diff_summary
ref_type = raw_segment | raw_document | section | publish_version | source_mapping
ref_id = 对应业务 ID
publish_version_id = 当前 staging / active 版本 ID
```

### 6.2 Serving 场景

Serving 可用 LLM 做查询理解和上下文压缩，但不能替代底层检索。

适合场景：

| 场景 | 输入 | 输出 | 使用方式 |
|---|---|---|---|
| query rewrite | 用户 query + scope | 多个检索 query | 输入 QueryPlan |
| intent extraction | query | intent/entities/facets | 输入 QueryPlan |
| context compression | evidence items | compressed context | 输出给 Agent/Skill |
| rerank explanation | candidates | rerank rationale | debug/trace |
| answer draft | context pack | draft answer | 可选，默认仍由上层 Agent 最终回答 |

Serving 调用必须带：

```text
caller_domain = serving
pipeline_stage = query_rewrite | intent_extraction | rerank | context_compression | answer_draft
ref_type = query | request | context_pack | retrieval_trace
ref_id = query_id / request_id / context_pack_id
```

## 7. 数据表需求

第一版建议新增 SQLite/PostgreSQL 双 DDL，类似当前 asset schema 的做法。

### 7.1 `agent_llm_tasks`

记录一次逻辑 LLM 任务。

| 字段 | 要求 |
|---|---|
| `id` | task id |
| `caller_domain` | `mining/serving/...` |
| `pipeline_stage` | 调用阶段 |
| `ref_type` | 业务关联对象类型 |
| `ref_id` | 业务关联对象 ID |
| `publish_version_id` | Mining/Serving 涉及资产版本时填写 |
| `request_id` | Serving 在线请求 ID，可选但建议有 |
| `idempotency_key` | 幂等键，防重复提交 |
| `status` | `queued/running/succeeded/failed/cancelled/dead_letter` |
| `priority` | 队列优先级 |
| `available_at` | 延迟执行/重试时间 |
| `attempt_count` | 已尝试次数 |
| `max_attempts` | 最大尝试次数 |
| `created_at/updated_at/started_at/finished_at` | 生命周期时间 |
| `metadata_json` | 扩展信息 |

### 7.2 `agent_llm_requests`

记录模型调用输入。

| 字段 | 要求 |
|---|---|
| `id` | request id |
| `task_id` | 关联 task |
| `provider` | `anthropic/openai/local/mock/...` |
| `model` | 模型名 |
| `prompt_template_key` | prompt 模板标识 |
| `prompt_template_version` | prompt 版本 |
| `messages_json` | 实际 messages |
| `input_json` | 结构化输入 |
| `params_json` | temperature/max_tokens 等 |
| `expected_output_type` | `json_object/json_array/text` |
| `output_schema_key` | 预期 schema 名 |
| `output_schema_json` | 可选 JSON schema |
| `created_at` | 创建时间 |

### 7.3 `agent_llm_attempts`

记录每次实际 provider 调用。

| 字段 | 要求 |
|---|---|
| `id` | attempt id |
| `task_id` | 关联 task |
| `request_id` | 关联 request |
| `attempt_no` | 第几次尝试 |
| `status` | `running/succeeded/failed/timeout/rate_limited` |
| `provider_request_id` | provider 返回的请求 ID |
| `raw_output_text` | 原始输出 |
| `raw_response_json` | provider 原始响应摘要 |
| `error_type/error_message` | 错误 |
| `prompt_tokens/completion_tokens/total_tokens` | token 统计 |
| `latency_ms` | 耗时 |
| `started_at/finished_at` | 时间 |

### 7.4 `agent_llm_results`

记录最终解析结果。

| 字段 | 要求 |
|---|---|
| `id` | result id |
| `task_id` | 关联 task |
| `attempt_id` | 成功 attempt |
| `parse_status` | `not_required/succeeded/failed/schema_invalid` |
| `parsed_output_json` | 解析后的 JSON |
| `text_output` | 文本输出 |
| `parse_error` | 解析错误 |
| `validation_errors_json` | schema 校验错误 |
| `confidence` | 可选置信度 |
| `created_at` | 创建时间 |

### 7.5 `agent_llm_events`

可选但建议有，用于排查队列和状态流转。

| 字段 | 要求 |
|---|---|
| `id` | event id |
| `task_id` | 关联 task |
| `event_type` | `submitted/claimed/retried/succeeded/failed/cancelled` |
| `message` | 短消息 |
| `metadata_json` | 事件上下文 |
| `created_at` | 时间 |

## 8. 队列状态机

建议状态：

```text
queued
  -> running
  -> succeeded
  -> failed
  -> dead_letter
  -> cancelled
```

重试规则：

- provider 429、timeout、临时网络错误：可重试。
- JSON parse failed：默认不重试，除非调用方配置 `retry_on_parse_error = true`。
- schema invalid：默认不重试，应保留原始输出供调试。
- 超过 `max_attempts` 后进入 `dead_letter`。

Worker claim 规则：

- 只 claim `status = queued AND available_at <= now`。
- claim 时原子更新为 `running`，写 `started_at`。
- 支持 `priority DESC, created_at ASC`。
- 需要处理进程崩溃后 `running` 长时间未完成的恢复，例如 `lease_expires_at`。

## 9. JSON 解析需求

解析器必须支持：

1. 直接 JSON。
2. Markdown fenced code block 中的 JSON。
3. provider 返回前后夹杂解释文字时，尽力提取第一段合法 JSON。
4. 输出类型为 array/object 时做类型校验。
5. schema 校验失败时保存 validation errors。

解析器不能做：

- 不能静默把非法 JSON 当空对象。
- 不能覆盖 `raw_output_text`。
- 不能因为 parse failed 就丢掉 task 的审计记录。

## 10. API / Client 契约

建议提供两个调用方式。

### 10.1 异步提交

```python
task = await llm_client.submit(
    caller_domain="mining",
    pipeline_stage="retrieval_unit_generation",
    ref_type="raw_segment",
    ref_id=raw_segment_id,
    publish_version_id=publish_version_id,
    prompt_template_key="mining.retrieval_unit.v1",
    input_json={...},
    expected_output_type="json_object",
    output_schema_key="RetrievalUnitDraft",
    idempotency_key=f"retrieval-unit:{publish_version_id}:{raw_segment_id}",
)
```

### 10.2 同步执行

Serving 在线链路可能需要同步调用，但必须可配置超时。

```python
result = await llm_client.run_sync(
    caller_domain="serving",
    pipeline_stage="query_rewrite",
    ref_type="query",
    ref_id=query_id,
    request_id=request_id,
    timeout_ms=3000,
    input_json={...},
    expected_output_type="json_object",
)
```

同步执行也必须落库，本质上只是提交后立即执行或等待结果。

## 11. 与现有系统的关系

### 11.1 对 Mining 的影响

Mining 当前 pipeline 是：

```text
ingest -> profile -> parse -> segment -> canonicalize -> publish
```

新增 runtime 后，不应直接插入到所有步骤里。建议从可旁路的增强点开始：

```text
segment -> optional LLM enrichment -> retrieval unit generation -> publish
```

如果后续采用 dev 笔记中的 retrieval unit 主路径，LLM runtime 可以用于 `generated_question/summary/contextual_text` 的生成，但生成结果必须记录 `task_id/result_id`。

### 11.2 对 Serving 的影响

Serving 当前是规则 Normalizer + QueryPlan + canonical search + drilldown + EvidencePack。

新增 runtime 后，第一阶段不应强制在线请求都调用 LLM。建议按开关启用：

```text
LLM_QUERY_REWRITE_ENABLED=false
LLM_CONTEXT_COMPRESSION_ENABLED=false
```

开启后，LLM 只增强 QueryPlan 或压缩 ContextPack，不替代 repository 检索和 source audit。

### 11.3 对 schema 的影响

现有 `asset_*` 六张表不适合承载 LLM 调用日志。应新增 runtime 自有 DDL：

```text
knowledge_assets/schemas/002_agent_llm_runtime.sql
knowledge_assets/schemas/002_agent_llm_runtime.sqlite.sql
```

或者如果希望 runtime 完全独立，也可以放：

```text
agent_runtime/schemas/001_agent_llm_runtime.sql
agent_runtime/schemas/001_agent_llm_runtime.sqlite.sql
```

但初始化入口必须统一，否则 dev SQLite 容易出现 Mining/Serving/Runtime 三套 schema 漂移。

## 12. 关键验收标准

第一版完成后至少要能证明：

1. Mining 可以提交一个 `caller_domain=mining` 的 LLM 任务，并通过 `raw_segment_id` 查回结果。
2. Serving 可以提交一个 `caller_domain=serving` 的 LLM 任务，并通过 `query_id/request_id` 查回结果。
3. 每次调用都保存 prompt/messages、input、raw output、parsed JSON、parse status。
4. JSON fenced block 可以被解析。
5. 非法 JSON 会记录 parse failed 和原始输出。
6. 队列 worker 能 claim queued task，执行成功后更新 succeeded。
7. provider 临时失败会重试，超过次数进入 dead_letter。
8. idempotency_key 能防止同一业务对象重复生成多条未完成任务。
9. Runtime 不 import Mining/Serving。
10. Mining/Serving 不直接写 runtime 表，必须走 client/repository。

## 13. 主要风险

### P1: 把 LLM 结果当作事实写入资产层

LLM 输出可能是摘要、候选、解释或改写，不等于原始事实。任何写入 `asset_*` 主表的 LLM 结果都必须保留 provenance，并区分 generated / extracted / source-derived。

### P1: 在线 Serving 被 LLM 延迟拖垮

Serving 在线请求不能默认依赖 LLM。Query rewrite / compression 必须有超时和 fallback，失败时继续走规则检索。

### P1: 队列与发布版本不一致

Mining 的异步 LLM 任务如果绑定 staging publish version，而该版本最终 failed 或被新版本替代，结果不能误写到 active 资产。必须用 `publish_version_id` 和 `ref_id` 约束结果归属。

### P2: JSON 解析过度宽松

解析器可以尽力提取 JSON，但不能在 schema invalid 时伪装成功。否则后续 pipeline 会消费脏结构。

### P2: 表设计只放一个 related_id

单字段关联短期方便，长期会混淆 mining job、raw segment、serving request、context pack。必须至少有 `caller_domain/ref_type/ref_id`，并按需保留 `publish_version_id/request_id`。

### P2: Prompt 版本不可追踪

如果不保存 `prompt_template_key/version`，后续无法解释同一段 raw segment 为什么生成不同 entity/summary。

## 14. 建议拆分

建议将该需求拆成一个新的正式任务，不并入现有 Mining 或 Serving 修复任务。

建议 task id：

```text
TASK-20260420-agent-llm-runtime
```

建议阶段：

| 阶段 | 内容 |
|---|---|
| M0 | runtime schema + client + JSON parser + mock provider |
| M1 | SQLite queue worker + attempts/results/events + tests |
| M2 | Mining 接入一个离线增强场景，例如 retrieval unit draft |
| M3 | Serving 接入可关闭的 query rewrite 场景 |
| M4 | provider 插件化、成本统计、超时/重试策略固化 |

## 15. 最终评估

该模块应该作为独立系统建设。它既不是 Mining 的插件，也不是 Serving 的 helper，而是跨 pipeline 的 LLM 调用基础设施。

第一版的核心不是把 LLM 接起来，而是把调用审计、业务关联、JSON 解析、队列、重试、幂等和结果归属做稳。只要这些边界定住，Mining 可以安全地用 LLM 做离线增强，Serving 可以谨慎地用 LLM 做 query rewrite / context compression，并且所有结果都能通过 mining/query 侧 ID 回溯。
