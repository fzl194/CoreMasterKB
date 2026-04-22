# LLM Service 接入指南

> **稳定性承诺**: 本文档定义的接口为稳定合同。LLM Service 内部实现可以自由演进，但对外接口不经版本升级不会变更。

## 核心原则

| 层 | 允许变化 |
|---|---|
| LLM Service 内部（DB、Worker、Recovery、Provider） | 可以变 |
| **API 端点 + LLMClient 调用方式** | **不能变** |
| **请求 / 响应结构** | **不能变** |
| **metadata 扩展入口** | **不能变** |

LLM Service 内部重构（换 DB、拆 Worker、改表结构）时，调用方无需改代码。

---

## 快速开始

### 启动服务

```bash
# 必须设置
export LLM_SERVICE_PROVIDER_API_KEY=your-api-key

# 可选配置
export LLM_SERVICE_PROVIDER_BASE_URL=https://api.deepseek.com
export LLM_SERVICE_PROVIDER_MODEL=deepseek-chat
export LLM_SERVICE_PROVIDER_BYPASS_PROXY=false  # 内网机器无法访问 LLM 时设为 true

python -m llm_service
# 监听 http://0.0.0.0:8900
```

### 初始化客户端

```python
from llm_service.client import LLMClient

client = LLMClient(base_url="http://localhost:8900")
```

---

## 两种接入模式

### 模式 A：Mining（批量异步）

Mining 提交大量任务，Worker 后台执行，Mining 轮询获取结果。

```python
# 1. 批量提交
task_ids = []
for section in sections:
    tid = await client.submit(
        caller_domain="mining",
        pipeline_stage="retrieval_units",
        template_key="mining-question-gen",
        input={"section_title": section.title, "content": section.text},
        metadata={
            "caller_context": {
                "ref": {"type": "section", "id": section.id},
                "build_id": build_id,
            }
        },
    )
    task_ids.append(tid)

# 2. 轮询结果
for tid in task_ids:
    task = await client.get_task(tid)
    if task["status"] == "succeeded":
        result = await client.get_result(tid)
        questions = result["parsed_output"]
```

### 模式 B：Serving（同步在线）

Serving 需要立即获得结果——查询改写、实体提取、重排序等。

```python
# 同步调用——阻塞等待 LLM 返回
result = await client.execute(
    caller_domain="serving",
    pipeline_stage="normalizer",
    template_key="serving-query-rewrite",
    input={"query": user_query},
    metadata={"caller_context": {"request_id": req_id}},
)
rewritten = result["result"]["parsed_output"]
```

### 模式 C：直接传 messages（不用模板）

```python
result = await client.execute(
    caller_domain="serving",
    pipeline_stage="rerank",
    messages=[
        {"role": "system", "content": "按相关性重排序。"},
        {"role": "user", "content": f"Query: {q}\nDocs: {docs}"},
    ],
    expected_output_type="json_array",
)
```

---

## API 参考

### `client.submit(...) -> str`

异步提交任务，返回 `task_id`。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `caller_domain` | str | 是 | — | 调用方域名（如 "mining"、"serving"） |
| `pipeline_stage` | str | 是 | — | 流水线阶段（如 "extract"、"normalizer"） |
| `template_key` | str | 否 | None | 已注册的模板 key |
| `input` | dict | 否 | None | 模板变量（配合 template_key 使用） |
| `messages` | list[dict] | 否 | None | 直接传 chat messages（跳过模板） |
| `params` | dict | 否 | None | Provider 参数（temperature 等） |
| `expected_output_type` | str | 否 | "json_object" | "json_object" / "json_array" / "text" |
| `output_schema` | dict | 否 | None | JSON Schema，用于验证输出 |
| `idempotency_key` | str | 否 | None | 幂等 key，相同 key 返回相同 task_id |
| `metadata` | dict | 否 | None | 调用方上下文，原样存储和返回 |
| `max_attempts` | int | 否 | 3 | 最大重试次数（1-10） |
| `priority` | int | 否 | 100 | 优先级，数值越小越优先 |

### `client.execute(...) -> dict`

同步调用——提交 + 执行 + 返回结果。参数同 `submit()`。

**返回结构：**

```json
{
    "task_id": "uuid",
    "status": "succeeded",
    "attempts": 1,
    "total_tokens": 150,
    "latency_ms": 2300,
    "result": {
        "parse_status": "succeeded",
        "parsed_output": {"key": "value"},
        "text_output": null,
        "validation_errors": []
    },
    "error": null
}
```

### `client.get_task(task_id) -> dict`

**稳定返回字段：**

```json
{
    "id": "uuid",
    "caller_domain": "mining",
    "pipeline_stage": "extract",
    "status": "succeeded",
    "idempotency_key": null,
    "priority": 100,
    "attempt_count": 1,
    "max_attempts": 3,
    "metadata": {"caller_context": {...}},
    "created_at": "2026-04-22T10:00:00+00:00",
    "updated_at": "2026-04-22T10:00:02+00:00",
    "started_at": "2026-04-22T10:00:01+00:00",
    "finished_at": "2026-04-22T10:00:02+00:00"
}
```

### `client.get_result(task_id) -> dict`

**稳定返回字段：**

```json
{
    "id": "uuid",
    "task_id": "uuid",
    "parse_status": "succeeded",
    "parsed_output": {"summary": "..."},
    "text_output": null,
    "parse_error": null,
    "validation_errors": [],
    "created_at": "2026-04-22T10:00:02+00:00"
}
```

### `client.get_attempts(task_id) -> list[dict]`

**每条 attempt 稳定返回字段：**

```json
{
    "id": "uuid",
    "task_id": "uuid",
    "attempt_no": 1,
    "status": "succeeded",
    "error_type": null,
    "error_message": null,
    "prompt_tokens": 50,
    "completion_tokens": 100,
    "total_tokens": 150,
    "latency_ms": 2300,
    "started_at": "...",
    "finished_at": "..."
}
```

### `client.get_events(task_id) -> list[dict]`

```json
{
    "id": "uuid",
    "task_id": "uuid",
    "event_type": "submitted",
    "message": "task submitted",
    "created_at": "..."
}
```

### `client.cancel(task_id) -> dict`

返回 `{"task_id": "...", "status": "cancelled"}`。仅对 `queued` 状态的任务有效。

---

## 任务生命周期

```
                     submit()
                        |
                    [queued] ---- cancel() --> [cancelled]
                        |
                     claim()
                        |
                    [running] ---- 超时 --> (lease recovery 处理)
                        |
              +---------+---------+
              |                   |
           成功               失败 + 重试
              |                   |
         [succeeded]        [queued]（退避等待）
                                  |
                           ... 达到最大重试 ...
                                  |
                           [dead_letter]
```

---

## 模板系统

模板预定义 prompt，调用方只需传 `template_key` + `input` 变量。

### 创建模板

```bash
POST /api/v1/templates
{
    "template_key": "mining-question-gen",
    "template_version": "1",
    "purpose": "从内容生成问答对",
    "system_prompt": "你是知识挖掘助手。",
    "user_prompt_template": "根据以下内容生成问答：$content",
    "expected_output_type": "json_array"
}
```

### 使用模板

```python
result = await client.execute(
    caller_domain="mining",
    pipeline_stage="extract",
    template_key="mining-question-gen",
    input={"content": "Python是一种编程语言。"},
)
```

`user_prompt_template` 中用 `$var` 语法定义占位符，`input` 字典的 key 会被替换。

---

## metadata 约定

`metadata` 是自由格式的 dict，LLM Service 原样存储、原样返回，不影响执行逻辑。

推荐结构：

```python
metadata = {
    "caller_context": {
        "request_id": "req-123",
        "build_id": "build-456",
        "ref": {"type": "section", "id": "sec-789"},
    }
}
```

用途：
- **可追溯性**：将 LLM 任务与业务实体关联
- **调试**：在 Dashboard 上按业务上下文查找任务
- **未来扩展**：新增字段不会破坏现有调用

---

## 幂等控制

提供 `idempotency_key` 时：
- 首次调用创建新任务
- 后续相同 key 的调用返回同一个 `task_id`
- `submit()` 和 `execute()` 均支持

```python
# 可以安全地多次调用
result = await client.execute(
    caller_domain="serving",
    pipeline_stage="normalizer",
    messages=[{"role": "user", "content": "hello"}],
    idempotency_key="unique-per-operation-123",
)
```

---

## 错误处理

### execute() 返回处理

```python
result = await client.execute(...)

if result["status"] == "succeeded":
    data = result["result"]["parsed_output"]
elif result["status"] == "dead_letter":
    err = result["error"]
    print(f"失败: {err['error_type']}: {err['error_message']}")
elif result["status"] == "running":
    # 超时——任务仍在后台执行，稍后通过 get_task() 轮询
    task_id = result["task_id"]
```

### parse_status 含义

| 值 | 含义 |
|---|---|
| `succeeded` | 输出解析成功 |
| `failed` | 输出无法按预期类型解析 |
| `schema_invalid` | 解析成功但未通过 schema 验证 |

---

## HTTP 端点一览

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/v1/tasks` | 异步提交 |
| POST | `/api/v1/execute` | 同步执行 |
| GET | `/api/v1/tasks/{id}` | 查询任务 |
| POST | `/api/v1/tasks/{id}/cancel` | 取消任务 |
| GET | `/api/v1/tasks/{id}/result` | 查询结果 |
| GET | `/api/v1/tasks/{id}/attempts` | 查询执行记录 |
| GET | `/api/v1/tasks/{id}/events` | 查询事件时间线 |
| POST | `/api/v1/templates` | 创建模板 |
| GET | `/api/v1/templates` | 列出模板 |
| GET | `/api/v1/templates/{key}` | 按 key 查询模板 |
| PUT | `/api/v1/templates/{id}` | 更新模板 |
| DELETE | `/api/v1/templates/{id}` | 归档模板 |
| GET | `/health` | 健康检查 |
| GET | `/dashboard` | Web 看板 |

---

## 稳定性保障

1. 上述请求参数和返回结构**不会发生破坏性变更**
2. 新功能通过**可选参数**添加，不影响现有调用
3. `metadata` 是领域上下文的唯一扩展入口
4. LLM Service 内部重构（换 DB、拆 Worker、改表结构）**不需要调用方改动代码**
