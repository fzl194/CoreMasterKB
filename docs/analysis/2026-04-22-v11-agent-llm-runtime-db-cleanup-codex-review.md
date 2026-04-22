# LLM Runtime DB 去业务化清理建议

## 背景

- 任务：`TASK-20260421-v11-agent-llm-runtime`
- 目的：基于当前 `llm_service` 实现、`agent_llm_runtime` 现有 schema，以及 v1.1 总体架构边界，整理一版可直接交给 `Claude LLM` 执行的数据库清理方案。
- 本文不讨论 provider 逻辑、worker 并发或模板执行链修复；只讨论 **LLM Runtime 的表结构职责收口**。

## 当前实现的关键事实

### 1. `task` 是对外主入口，不是 `request`

当前 API 和运行时主链都是：

```text
submit/execute -> task -> request -> attempt -> result -> event
```

调用方提交后拿到的是 `task_id`，轮询和排障首先看的也是 task。

因此，去业务化之后仍要满足一个要求：

```text
业务查 task 时，仍能看到足够的 caller context
```

但这不等于要继续在 `agent_llm_tasks` 上保留一组分散业务列。

### 2. 当前 schema 里确实有一批“被动透传字段”

当前这些字段主要在 API -> service -> task/request 落库时透传，**不参与 runtime 内核逻辑**：

- `agent_llm_tasks.ref_type`
- `agent_llm_tasks.ref_id`
- `agent_llm_tasks.build_id`
- `agent_llm_tasks.release_id`
- `agent_llm_tasks.request_id`

它们当前不驱动：

- 状态机
- claim/retry
- worker/recovery
- template 解析
- parse/result

因此，这批字段具备清理条件。

### 3. `request_id` 当前语义混乱，确实应从显式合同里退场

当前实现里：

- `tasks.request_id` 记录调用方 request id
- `requests.id` 又一度复用了调用方 request id
- `attempts.request_id` 指向 request 行主键

这会把：

- 调用方链路编号
- 内部 request 记录主键

混成一个概念。

从 runtime 设计上看，这不是好合同。

### 4. `idempotency_key` 和 `request_id` 不是一个语义层

- `idempotency_key` 的职责是：控制“是否复用已有 task”
- `request_id` 的职责如果继续存在，只会是“调用方自己的链路编号”

但当前 runtime 并不依赖“调用方链路编号”来驱动任何核心逻辑。

如果保留一个新的 `caller_request_id` 独立列，本质上只是把旧问题换了个名字，而没有提升 runtime 内核能力。

因此，本文建议：

```text
不新增 caller_request_id 列
```

如果调用方需要跨系统追踪自己的 request id，应放进 `metadata_json`，而不是再给 runtime 增一个专用字段。

## 设计原则

| 原则 | 说明 |
|---|---|
| Runtime 去业务化 | `agent_llm_runtime` 是通用 LLM 调用与审计底座，不承载 Mining/Serving 的业务模型。 |
| `task` 仍是外部入口对象 | 业务首先拿到和查看的是 `task`，因此入口级 caller context 需要能从 task 直接看到。 |
| 显式列只保留 runtime 自己用的字段 | 只有状态机、调度、执行、审计直接依赖的字段，才保留为独立列。 |
| 不再给 caller tracing 单独加列 | `request_id` 不保留，`caller_request_id` 也不新增；若调用方要链路编号，进入 `metadata_json`。 |
| 内部 ID 和调用方上下文彻底解耦 | 所有主键、关联键都由 runtime 自己生成，不再混用调用方输入。 |
| 入口上下文统一收口 | caller 的业务锚点和链路摘要统一收口到 `tasks.metadata_json`，不再散落成多个列。 |
| request 层只记录请求载荷 | `agent_llm_requests` 保持为“本次调用具体发了什么”的表，不再背 caller 业务字段。 |
| YAGNI | 代码未使用、合同未立住、未来也无明确近期收益的空壳字段，直接删除。 |

## 总体收口方案

### 核心决策

```text
agent_llm_tasks = 纯 task 状态机 + task 入口级 metadata
agent_llm_requests = 纯 request 载荷
agent_llm_attempts = 单次尝试审计
agent_llm_results = 解析结果
agent_llm_events = 生命周期流水
```

也就是说：

- caller 的业务锚点不再用显式列表达
- 但也不挪到 request 才能看到
- 而是统一放到 `tasks.metadata_json`

这样既满足去业务化，也保住了 task 作为外部入口对象的可观察性。

## 逐表目标结构

### 1. `agent_llm_prompt_templates`

| 字段 | 处理 | 理由 |
|---|---|---|
| `id` | 保留 | 内部主键。 |
| `template_key` | 保留 | 运行时查模板主标识。 |
| `template_version` | 保留 | 模板版本化。 |
| `purpose` | 保留 | 模板用途说明。 |
| `system_prompt` | 保留 | 模板内容。 |
| `user_prompt_template` | 保留 | 模板内容。 |
| `expected_output_type` | 保留 | 模板执行默认合同。 |
| `output_schema_key` | 删除 | 当前完全未被代码写入或读取。 |
| `output_schema_json` | 保留 | 模板 schema 默认值。 |
| `status` | 保留 | draft/active/archived。 |
| `created_at` | 保留 | 审计字段。 |
| `metadata_json` | 保留 | 低频扩展字段。 |

### 2. `agent_llm_tasks`

| 字段 | 处理 | 理由 |
|---|---|---|
| `id` | 保留 | task 主键，也是调用方主入口。 |
| `caller_domain` | 保留，但去掉 DB CHECK 枚举 | 这是 runtime 自己的观测维度，不属于业务字段；但不应靠 schema 限死枚举。 |
| `pipeline_stage` | 保留 | 这是 runtime 自己的调用阶段维度。 |
| `ref_type` | 删除 | 属于 caller 业务锚点，不驱动 runtime 内核。 |
| `ref_id` | 删除 | 同上。 |
| `build_id` | 删除 | 同上。 |
| `release_id` | 删除 | 同上。 |
| `request_id` | 删除 | 与内部 request identity 语义混乱，且不参与 runtime 核心逻辑。 |
| `idempotency_key` | 保留 | runtime 幂等语义字段，必须保留。 |
| `status` | 保留 | task 状态机核心字段。 |
| `priority` | 保留 | 调度字段。 |
| `available_at` | 保留 | backoff / retry 调度字段。 |
| `lease_expires_at` | 保留 | recovery 判断字段。 |
| `attempt_count` | 保留 | 重试控制字段。 |
| `max_attempts` | 保留 | 重试上限。 |
| `created_at` | 保留 | 审计。 |
| `updated_at` | 保留 | 审计。 |
| `started_at` | 保留 | 状态跟踪。 |
| `finished_at` | 保留 | 状态跟踪。 |
| `metadata_json` | 保留，并升级为 task 入口级 caller context 容器 | 去业务化后 caller 上下文的唯一正式落点。 |

### 3. `agent_llm_requests`

| 字段 | 处理 | 理由 |
|---|---|---|
| `id` | 保留，但强制内部 UUID | request 行主键必须由 runtime 自己生成。 |
| `task_id` | 保留 | request 归属 task。 |
| `provider` | 保留 | 请求载荷与审计。 |
| `model` | 保留 | 请求载荷与审计。 |
| `prompt_template_key` | 保留 | 记录本次请求使用了哪个模板 key。 |
| `prompt_template_version` | 删除 | 当前实现未写入，合同未立住。 |
| `messages_json` | 保留 | 真正发送给 provider 的请求载荷。 |
| `input_json` | 保留 | 模板展开输入留档。 |
| `params_json` | 保留 | provider 参数留档。 |
| `expected_output_type` | 保留 | 最终执行合同。 |
| `output_schema_key` | 删除 | 当前未写入、未使用。 |
| `output_schema_json` | 保留 | 最终执行 schema 合同。 |
| `created_at` | 保留 | 审计字段。 |
| `metadata_json` | 保留 | 仅用于 request 级附加扩展，不再承担 caller 主上下文。 |

### 4. `agent_llm_attempts`

| 字段 | 处理 | 理由 |
|---|---|---|
| `id` | 保留 | attempt 主键。 |
| `task_id` | 保留 | 审计链归属。 |
| `request_id` | 保留 | 指向内部 request 主键。 |
| `attempt_no` | 保留 | 第几次尝试。 |
| `status` | 保留 | attempt 状态。 |
| `provider_request_id` | 删除 | 当前没有代码消费；raw response 已可留底。 |
| `raw_output_text` | 保留 | 原始输出。 |
| `raw_response_json` | 保留 | 原始 provider 响应。 |
| `error_type` | 保留 | 错误分类。 |
| `error_message` | 保留 | 错误详情。 |
| `prompt_tokens` | 保留 | 成本与审计。 |
| `completion_tokens` | 保留 | 成本与审计。 |
| `total_tokens` | 保留 | 成本与审计。 |
| `latency_ms` | 保留 | 性能审计。 |
| `started_at` | 保留 | 审计。 |
| `finished_at` | 保留 | 审计。 |
| `metadata_json` | 保留 | 低频扩展。 |

### 5. `agent_llm_results`

| 字段 | 处理 | 理由 |
|---|---|---|
| `id` | 保留 | result 主键。 |
| `task_id` | 保留 | 结果查询主路径。 |
| `attempt_id` | 保留 | 回溯到来源 attempt。 |
| `parse_status` | 保留 | 解析结果状态。 |
| `parsed_output_json` | 保留 | 结构化输出。 |
| `text_output` | 保留 | 文本输出。 |
| `parse_error` | 保留 | 解析错误。 |
| `validation_errors_json` | 保留 | schema 校验错误。 |
| `confidence` | 删除 | 当前完全未写入，也没有统一语义。 |
| `created_at` | 保留 | 审计。 |
| `metadata_json` | 保留 | 低频扩展。 |

### 6. `agent_llm_events`

| 字段 | 处理 | 理由 |
|---|---|---|
| 全字段 | 保留 | 事件流水本身已经足够轻，且每个字段都服务于 runtime 生命周期审计。 |

## 推荐的 `metadata_json` 职责划分

### `agent_llm_tasks.metadata_json`

这是去业务化之后的**正式 caller context 落点**。

建议统一承接：

- 调用方自己的 request/tracing id
- 业务锚点
- build/release 等运行上下文
- 仅用于排障和观测的 caller tags

推荐结构示例：

```json
{
  "caller_context": {
    "request_id": "req-001",
    "ref": {
      "type": "section",
      "id": "sec-001"
    },
    "build_id": "build-2026-04-22",
    "release_id": "release-prod-2026-04-22"
  },
  "tags": ["mining", "question_gen"]
}
```

这里的 key 只是**推荐约定**，不是 runtime schema 合同。  
也就是说 runtime 不理解这些字段的业务语义，只负责存储和返回。

### `agent_llm_requests.metadata_json`

只保留给 request 级附加信息，例如：

- 本次 prompt 构造辅助信息
- provider 特定扩展参数留底
- 非核心的调试附加信息

不建议再把 caller 主上下文在 task/request 两层重复写一遍。

## 为什么不新增 `caller_request_id`

| 判断点 | 结论 |
|---|---|
| runtime 是否依赖它做幂等？ | 不依赖。幂等已经由 `idempotency_key` 表达。 |
| runtime 是否依赖它做 request/attempt/result 关联？ | 不依赖。内部用主键链已足够。 |
| 它是否是 runtime 世界模型的一部分？ | 不是。它只是调用方自己的链路编号。 |
| 若新增这一列，是否会提升 runtime 核心能力？ | 不会，只会形成新的“半业务字段”。 |
| 如果调用方确实需要它怎么办？ | 放入 `tasks.metadata_json.caller_context.request_id`。 |

因此，本文建议：

```text
不新增 agent_llm_requests.caller_request_id
```

## 对 API / Client / UI 的连带修改

### API / Pydantic 模型

应从 `TaskSubmitRequest` 中移除顶层字段：

- `ref_type`
- `ref_id`
- `build_id`
- `release_id`
- `request_id`

同时保留并强化：

- `metadata: dict[str, Any] | None`

由调用方把这些 caller 上下文放进 metadata。

### `LLMClient`

`submit()` / `execute()` 不再单独接受：

- `ref_type`
- `ref_id`
- `build_id`
- `release_id`
- `request_id`

改为统一接受：

- `metadata: dict[str, Any] | None`

Mining / Serving 若要带上下文，都走 metadata。

### Dashboard / Task Detail 页面

当前固定渲染：

- `Build ID`
- `Release ID`
- `Ref`

这部分应改成：

- 直接展示 `metadata_json`
- 或展示一个 task metadata 摘要块

而不是继续假定 runtime 理解这些固定业务字段。

### 测试

需要同步替换：

- `request_id persisted` 相关测试
- `ref_type/ref_id/build_id/release_id` 透传测试

改为：

- metadata 原样落库与返回测试
- task 入口可观测性测试
- request 内部主键自动生成测试

## 迁移建议

### 迁移目标

不是“兼容旧字段长期共存”，而是一次性收口到新合同。

### 推荐步骤

| 步骤 | 动作 |
|---|---|
| 1 | 先修改 `llm_service/models.py`、`client.py`、`runtime/service.py`、`runtime/task_manager.py`，让新写入路径不再依赖旧列。 |
| 2 | 新增 schema 迁移：把旧 `tasks.request_id/ref/build/release` 搬入 `tasks.metadata_json`。 |
| 3 | 重建 `agent_llm_tasks` 与 `agent_llm_requests` 表结构，移除旧列和空壳列。 |
| 4 | 调整 dashboard、README、QUICKSTART、测试，全部改用 metadata 语义。 |
| 5 | 最后更新 `databases/agent_llm_runtime/schemas/001_agent_llm_runtime.sqlite.sql` 与对应文档口径。 |

### 旧数据迁移建议

如果已有历史数据，迁移时建议把旧列收口成：

```json
{
  "caller_context": {
    "request_id": "<old request_id>",
    "ref": {
      "type": "<old ref_type>",
      "id": "<old ref_id>"
    },
    "build_id": "<old build_id>",
    "release_id": "<old release_id>"
  }
}
```

然后再删除旧列。

## 需要 Claude LLM 确认的事项

| 事项 | 我方建议 |
|---|---|
| `task` 是外部入口，但又要去业务化，如何兼顾？ | caller 主上下文统一进 `tasks.metadata_json`，不再占独立列。 |
| 是否需要新增 `caller_request_id`？ | 不需要；若调用方要链路号，进入 metadata。 |
| `request` 表是否还要承接业务上下文？ | 不建议。request 只记录请求载荷，caller 主上下文以 task 为准。 |
| `caller_domain` 是否仍保留显式列？ | 保留，但取消 DB 枚举 CHECK。它是 runtime 自己的观测维度，不是业务字段。 |
| `pipeline_stage` 是否仍保留显式列？ | 保留。它是 runtime 的执行阶段维度。 |

## 最终建议

这次清理不应停留在“删几个空壳字段”，而应完成一次明确的职责重分配：

```text
task = 状态机 + task 入口级 metadata
request = 请求载荷
attempt = 单次尝试
result = 解析结果
event = 生命周期流水
```

按这个口径改完之后，`agent_llm_runtime` 才算真正从“夹带 Mining/Serving 当前业务字段的半通用库”，收口成一个可长期演进的通用 runtime 底座。
