# LLM Service v1.1 交接文档

> 状态：已审查
> 修订：2026-04-21 | Claude LLM

## 任务目标

建设独立的 LLM Service（`llm_service/`），为 Mining/Serving 提供统一的 LLM 调用与审计能力。FastAPI 独立进程（端口 8900），独立 SQLite 数据库（WAL 模式）。

## 本次实现范围

完整的 14 个 Task，按 4 个 Phase 交付：

- **Phase 1 - Skeleton (T1-T6):** config/db/main/models/providers/event_bus/task_manager/parser
- **Phase 2 - API+Client (T7-T10):** executor/service/API routes/template registry/LLMClient
- **Phase 3 - Dashboard (T11-T12):** Jinja2+HTMX 看板 + stats API
- **Phase 4 - Tests+Docs (T13-T14):** 7 个集成测试 + README + `__main__.py` 入口

## 明确不在本次范围内

- Worker 后台调度循环（当前为同步 execute，异步 submit 需外部 worker）
- API 认证/鉴权（预留扩展点，当前为内网服务）
- 生产级 rate limiting
- DB schema 迁移框架（当前使用 executescript + IF NOT EXISTS）
- OpenAI streaming 支持

## 改动文件清单

### 新增文件（29 个）

**核心运行时：**
- `llm_service/__init__.py` / `__main__.py`
- `llm_service/config.py` — pydantic-settings，env prefix `LLM_SERVICE_`
- `llm_service/db.py` — init_db，WAL + FK + schema
- `llm_service/main.py` — create_app 工厂，lifespan + routes
- `llm_service/models.py` — Pydantic request/response models
- `llm_service/client.py` — LLMClient 正式交付客户端

**Provider 层：**
- `llm_service/providers/base.py` — ProviderProtocol + ProviderResponse + ProviderError
- `llm_service/providers/mock.py` — MockProvider（测试用）
- `llm_service/providers/openai_compatible.py` — DeepSeek/OpenAI 兼容 provider

**运行时引擎：**
- `llm_service/runtime/event_bus.py` — EventBus 写 agent_llm_events
- `llm_service/runtime/idempotency.py` — find_existing_task (succeeded>running>queued)
- `llm_service/runtime/task_manager.py` — submit/claim/complete/fail/cancel + backoff
- `llm_service/runtime/parser.py` — JSON/text 解析 + JSON Schema 校验
- `llm_service/runtime/executor.py` — retry loop + attempt + result 写入
- `llm_service/runtime/service.py` — LLMService 顶层编排
- `llm_service/runtime/template_registry.py` — prompt template CRUD

**API 层：**
- `llm_service/api/health.py` — GET /health
- `llm_service/api/tasks.py` — POST /tasks, POST /execute, GET /tasks/{id}, POST cancel
- `llm_service/api/results.py` — GET result/attempts/events

**Dashboard：**
- `llm_service/dashboard/views.py` — HTML dashboard + stats API
- `llm_service/templates/dashboard.html` — Jinja2+HTMX 暗色主题

**测试（62 个）：**
- `llm_service/tests/conftest.py` — db/config/api_client fixtures
- `llm_service/tests/test_skeleton.py` — 3 tests
- `llm_service/tests/test_models.py` — 4 tests
- `llm_service/tests/test_providers.py` — 4 tests
- `llm_service/tests/test_event_bus.py` — 2 tests
- `llm_service/tests/test_task_manager.py` — 9 tests
- `llm_service/tests/test_parser.py` — 7 tests
- `llm_service/tests/test_executor.py` — 4 tests
- `llm_service/tests/test_api.py` — 9 tests
- `llm_service/tests/test_client.py` — 4 tests
- `llm_service/tests/test_template_registry.py` — 6 tests
- `llm_service/tests/test_dashboard.py` — 3 tests
- `llm_service/tests/test_integration.py` — 7 tests

### 修改文件

- `pyproject.toml` — 添加 `llm_service*` 到 packages.find + jinja2/jsonschema 依赖
- `.env.example` — 添加 LLM_SERVICE_* 环境变量

## 关键设计决策

1. **单执行引擎**：`/tasks`（异步）和 `/execute`（同步）共享 Executor + Parser 内部管线
2. **原子 claim**：`claim()` 使用 `UPDATE ... WHERE id = (SELECT ...) RETURNING id` 避免并发竞争
3. **幂等语义**：succeeded > running > queued 优先链；failed/dead_letter 不阻塞新提交
4. **重试退避**：`2^attempt_no * base`，executor 读取 available_at 并 sleep
5. **Provider 工厂**：`create_app(provider_factory=...)` 注入，测试用 MockProvider，生产用 OpenAICompatibleProvider
6. **默认 Provider**：DeepSeek（api.deepseek.com / deepseek-chat）

## 已执行验证

- 62 个单元/集成测试全部通过（`pytest llm_service/tests/ -v`）
- DeepSeek 真实 API 端到端调用验证通过（execute 全流程：submit→run→parse→result）
- 代码自查：发现并修复 3 CRITICAL + 4 HIGH 问题（详见最新 commit）

## 未验证项

- 多 worker 并发 claim 压力测试（SQLite WAL 模式下 RETURNING 的并发行为）
- 长时间运行下的 lease recovery 机制（代码已实现但未覆盖端到端测试）
- OpenAI streaming 功能（未实现）
- 大量任务下的 dashboard 性能（无分页）

## 已知风险

1. **无认证**：所有 API 端点无鉴权，依赖内网隔离
2. **SQLite 并发上限**：WAL 模式支持单写多读，高并发写入场景需考虑升级到 PostgreSQL
3. **无后台 worker**：异步 submit 的任务需外部调度 claim()→run()，当前无内置 worker 线程
4. **OpenAI provider 每次请求新建连接**：httpx.AsyncClient 未复用（HIGH-4，可接受但非最优）

## 指定给 Codex 的审查重点

1. **数据库契约一致性**：验证 `llm_service` 使用的 6 张表与 `databases/agent_llm_runtime/schemas/001_agent_llm_runtime.sqlite.sql` 定义一致
2. **幂等规则正确性**：`idempotency.py` 的 succeeded>running>queued 优先链是否符合设计意图
3. **重试退避机制**：executor 读取 `available_at` 并 sleep 的逻辑是否与 TaskManager.fail() 的 backoff 计算一致
4. **API 入参校验完备性**：`TaskSubmitRequest` 的 caller_domain 白名单 + expected_output_type 枚举是否足够
5. **service.py execute() 的 timeout 处理**：asyncio.TimeoutError 后 fail() 是否会导致状态不一致

## 管理员本轮直接介入记录

- 用户指定使用 DeepSeek 作为默认 provider，提供了 API key
- 用户要求先自查代码再移交 Codex
