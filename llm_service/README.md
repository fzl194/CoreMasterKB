# LLM Service

统一 LLM 调用与审计服务，为 Mining / Serving 提供集中式的模型调用能力。

## 这是什么

LLM Service 是一个**独立运行的 FastAPI 服务**（端口 8900），拥有自己的 SQLite 数据库。

它的职责很单一：**统一管理所有 LLM 调用的提交、执行、重试、结果解析和审计记录**。

Mining 和 Serving 不各自维护 LLM 调用逻辑，而是通过 `LLMClient` 或 HTTP API 调用本服务。

```
┌─────────┐     ┌─────────┐
│ Mining  │     │ Serving │
└────┬────┘     └────┬────┘
     │               │
     │  LLMClient    │  LLMClient
     │               │
     └───────┬───────┘
             │
             ▼
    ┌─────────────────┐
    │  LLM Service    │  ← 你在这里
    │  (FastAPI:8900) │
    │  SQLite (WAL)   │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │  DeepSeek /     │
    │  OpenAI / ...   │
    └─────────────────┘
```

## 快速启动

```bash
# 1. 安装依赖
pip install -e .

# 2. 配置环境变量（可选，有默认值）
export LLM_SERVICE_PROVIDER_API_KEY=sk-your-key

# 3. 启动服务
python -m llm_service

# 4. 验证
curl http://localhost:8900/health
# → {"status":"ok"}

# 5. 打开看板
浏览器访问 http://localhost:8900/dashboard
```

## 两种调用模式

### 同步执行 — `execute()`

调用方**等结果**。适合需要立即拿到 LLM 输出的场景。

```python
from llm_service.client import LLMClient

client = LLMClient(base_url="http://localhost:8900")

result = await client.execute(
    caller_domain="mining",           # 谁在调用：mining / serving / ...
    pipeline_stage="section_summary", # 调用方的业务阶段名
    messages=[{"role": "user", "content": "请总结以下内容：..."}],
    expected_output_type="json_object", # 返回类型：json_object / json_array / text
)

# result 结构：
# {
#   "task_id": "uuid",
#   "status": "succeeded",
#   "attempts": 1,
#   "total_tokens": 128,
#   "latency_ms": 1523,
#   "result": {
#     "parse_status": "succeeded",
#     "parsed_output": {"summary": "..."},
#     "text_output": null,
#     "validation_errors": []
#   },
#   "error": null
# }
```

### 异步提交 — `submit()`

调用方**不等结果**，只拿 task_id。适合批量场景，后续自行轮询结果。

```python
# 提交
task_id = await client.submit(
    caller_domain="mining",
    pipeline_stage="question_gen",
    messages=[{"role": "user", "content": "生成3个问题"}],
    idempotency_key="doc-123-qgen",  # 幂等键，相同 key 不重复提交
)

# 后续查结果
task = await client.get_task(task_id)
result = await client.get_result(task_id)
attempts = await client.get_attempts(task_id)
events = await client.get_events(task_id)
```

## Mining 怎么调

Mining 在 pipeline 的 LLM 阶段（如 section_summary、question_gen、semantic_enrich）调用本服务：

```python
# Mining pipeline 中的典型用法
from llm_service.client import LLMClient

llm = LLMClient()

# 场景1：段落摘要 — 同步等结果
summary_result = await llm.execute(
    caller_domain="mining",
    pipeline_stage="section_summary",
    messages=[{"role": "user", "content": f"总结：{section_text}"}],
    expected_output_type="json_object",
    output_schema={"type": "object", "required": ["title", "summary"]},
    metadata={
        "caller_context": {
            "build_id": build_id,
            "release_id": release_id,
            "ref": {"type": "segment", "id": segment_id},
        }
    },
)
summary = summary_result["result"]["parsed_output"]

# 场景2：批量问题生成 — 带幂等
task_id = await llm.submit(
    caller_domain="mining",
    pipeline_stage="question_gen",
    messages=[{"role": "user", "content": f"基于以下内容生成问题：{content}"}],
    idempotency_key=f"seg-{segment_id}-qgen",
    max_attempts=3,
)
```

## Serving 怎么调

Serving 在检索链路的 LLM 阶段（如 query_rewrite、intent_extract、rerank）调用本服务：

```python
# Serving 检索链路中的典型用法
from llm_service.client import LLMClient

llm = LLMClient()

# 场景1：查询改写 — 同步执行
rewrite_result = await llm.execute(
    caller_domain="serving",
    pipeline_stage="query_rewrite",
    messages=[{"role": "user", "content": f"改写查询：{user_query}"}],
    expected_output_type="json_object",
    output_schema={
        "type": "object",
        "required": ["rewritten_query", "intent"],
        "properties": {
            "rewritten_query": {"type": "string"},
            "intent": {"type": "string"},
        },
    },
)
rewritten = rewrite_result["result"]["parsed_output"]["rewritten_query"]

# 场景2：意图/实体提取 — 文本返回
intent_result = await llm.execute(
    caller_domain="serving",
    pipeline_stage="intent_extract",
    messages=[{"role": "user", "content": f"提取意图：{query}"}],
    expected_output_type="text",
)
```

## API 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/v1/tasks` | 异步提交任务 |
| POST | `/api/v1/execute` | 同步执行（等结果） |
| GET | `/api/v1/tasks/{id}` | 查任务详情 |
| POST | `/api/v1/tasks/{id}/cancel` | 取消任务 |
| GET | `/api/v1/tasks/{id}/result` | 查解析结果 |
| GET | `/api/v1/tasks/{id}/attempts` | 查所有尝试 |
| GET | `/api/v1/tasks/{id}/events` | 查事件流水 |
| GET | `/dashboard` | Web 看板 |
| GET | `/dashboard/api/stats` | 统计 JSON |

## 环境变量配置

所有配置通过 `LLM_SERVICE_` 前缀的环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_SERVICE_HOST` | `0.0.0.0` | 绑定地址 |
| `LLM_SERVICE_PORT` | `8900` | 端口 |
| `LLM_SERVICE_DB_PATH` | `data/llm_service.sqlite` | 数据库路径 |
| `LLM_SERVICE_PROVIDER_BASE_URL` | `https://api.deepseek.com` | LLM API 地址 |
| `LLM_SERVICE_PROVIDER_API_KEY` | | API Key |
| `LLM_SERVICE_PROVIDER_MODEL` | `deepseek-chat` | 模型名 |
| `LLM_SERVICE_PROVIDER_BYPASS_PROXY` | `false` | 绕过系统代理（内网机器设 true） |
| `LLM_SERVICE_DEFAULT_MAX_ATTEMPTS` | `3` | 最大重试次数 |
| `LLM_SERVICE_LEASE_DURATION` | `300` | Worker 租约（秒） |
| `LLM_SERVICE_EXECUTE_TIMEOUT` | `60` | 同步执行超时（秒） |

## 核心概念

### 任务生命周期

```
queued → running → succeeded
                  → failed → (重试) → queued → ...
                  → dead_letter (耗尽重试次数)
         → cancelled
```

### 幂等控制

提交时可带 `idempotency_key`。相同 key 的重复提交不会创建新任务，而是返回已有任务的 ID。

优先级链：**succeeded > running > queued**（返回已有的）> **允许新建**。failed/dead_letter 不阻塞新提交。

### 重试与退避

失败后自动重试（指数退避：`2^attempt_no * base`），直到达到 `max_attempts`。所有尝试都记录在 `agent_llm_attempts` 表中。

### 结果解析

支持三种输出类型：
- `json_object`：解析为 JSON 对象，可附加 JSON Schema 校验
- `json_array`：解析为 JSON 数组
- `text`：原样返回文本

### 数据库表（6 张）

| 表 | 作用 |
|----|------|
| `agent_llm_prompt_templates` | Prompt 模板管理 |
| `agent_llm_tasks` | 任务主表 |
| `agent_llm_requests` | 请求参数（messages/params/schema） |
| `agent_llm_attempts` | 每次调用尝试（延迟/tokens/错误） |
| `agent_llm_results` | 解析结果（parsed/text/validation） |
| `agent_llm_events` | 事件流水（submitted/claimed/succeeded/failed） |

## 测试

```bash
pytest llm_service/tests/ -v
# 79 tests
```
