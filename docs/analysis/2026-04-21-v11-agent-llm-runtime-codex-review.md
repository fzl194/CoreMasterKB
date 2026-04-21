# TASK-20260421-v11-agent-llm-runtime Codex Review

## 审查背景

- 任务：`TASK-20260421-v11-agent-llm-runtime`
- 审查对象：Claude LLM 提交的 v1.1 `llm_service/` 独立运行时实现、对应 plan/handoff、与 `agent_llm_runtime` schema 契约的一致性
- 审查基线：
  - `docs/architecture/2026-04-21-coremasterkb-v1.1-architecture.md`
  - `docs/plans/2026-04-21-v11-llm-service-impl-plan.md`
  - `docs/plans/2026-04-21-llm-service-tdd-plan.md`
  - `docs/handoffs/2026-04-21-v11-llm-service-claude-llm-handoff.md`
  - `databases/agent_llm_runtime/schemas/001_agent_llm_runtime.sqlite.sql`
  - 提交链：`6894364` 到 `e7e9621`

## 审查范围

- `llm_service/` 运行时主链：config / db / main / models / client / runtime / api / dashboard / tests
- `pyproject.toml` 与 `.env.example`
- plan、TDD 计划、handoff 与最终代码的一致性

## 发现的问题

### P1. `/execute` 超时处理违反设计语义，并会留下不一致的 attempt 审计状态

- 设计文档明确要求：`execute` 超时时，task 继续保持 `running`，交给 lease recovery，不应直接失败。
- 实现中 `LLMService.execute()` 在 `asyncio.wait_for()` 超时后直接调用 `TaskManager.fail()`，把 task 回退到 `queued` 或 `dead_letter`。
- 同时 `Executor.run()` 没有显式处理 `CancelledError`，因此超时取消后可能留下 `agent_llm_attempts.status='running'` 的悬挂 attempt，而 task 主表已进入失败路径。
- 这会破坏“task / attempt / result / event”审计链的一致性，也与 plan 里的超时语义冲突。
- 代码位置：
  - `llm_service/runtime/service.py:145`
  - `llm_service/runtime/service.py:152`
  - `llm_service/runtime/task_manager.py:102`
  - `llm_service/runtime/executor.py:43`
- 文档位置：
  - `docs/plans/2026-04-21-v11-llm-service-impl-plan.md:307`
  - `docs/plans/2026-04-21-v11-llm-service-impl-plan.md:311`

### P1. Prompt template 平台只落了存储层，没有进入执行面，交付范围与计划声明不符

- plan/TDD 明确承诺了模板管理 API、模板管理页，以及基于模板的统一调用抽象。
- 最终实现中只有 `TemplateRegistry` 的 DB CRUD；主应用没有挂载模板路由，也没有 `/dashboard/templates` 页面。
- 更关键的是执行主链并不会根据 `template_key` 做模板查找、版本选择、prompt 展开；`template_key` 只是被原样写入 `agent_llm_requests`。
- 这意味着 Mining / Serving 仍需自行构造 `messages`，Runtime 尚未真正成为“统一 prompt/template 底座”。
- 代码位置：
  - `llm_service/main.py:51`
  - `llm_service/main.py:56`
  - `llm_service/runtime/service.py:77`
  - `llm_service/runtime/service.py:82`
  - `llm_service/runtime/template_registry.py:20`
- 文档位置：
  - `docs/plans/2026-04-21-v11-llm-service-impl-plan.md:174`
  - `docs/plans/2026-04-21-v11-llm-service-impl-plan.md:177`
  - `docs/plans/2026-04-21-v11-llm-service-impl-plan.md:197`
  - `docs/plans/2026-04-21-v11-llm-service-impl-plan.md:466`
  - `docs/plans/2026-04-21-llm-service-tdd-plan.md:1540`

### P1. `/tasks` 异步执行链未闭环，当前实现不能支撑计划中的批量 runtime 场景

- 当前运行时只有同步 `/execute` 会真正触发执行。
- `/tasks` 只会写入 `queued` task；应用启动时没有后台 worker，也没有任何自动 claim/run 循环。
- handoff 将 worker 标成“本次不在范围内”，但设计文档与 README 仍将 `/tasks` 描述为正式异步提交能力；这与 Mining 批量调用、调用方轮询语义直接相关。
- 结果是 Runtime 目前只能稳定支撑“同步在线增强”，不能支撑计划承诺的“统一异步任务 runtime”。
- 代码位置：
  - `llm_service/runtime/service.py:37`
  - `llm_service/runtime/task_manager.py:68`
  - `llm_service/main.py:24`
  - `llm_service/README.md:91`
- 文档位置：
  - `docs/plans/2026-04-21-v11-llm-service-impl-plan.md:216`
  - `docs/plans/2026-04-21-v11-llm-service-impl-plan.md:226`
  - `docs/plans/2026-04-21-v11-llm-service-impl-plan.md:282`
  - `docs/handoffs/2026-04-21-v11-llm-service-claude-llm-handoff.md:21`

### P2. 默认配置会读取仓库根 `.env`，在当前仓库环境下可直接导致服务和测试启动失败

- `LLMServiceConfig` 配置了 `env_file=".env"`，但模型未允许额外字段。
- 当前仓库根 `.env` 含有与 llm_service 无关的 `APP_ENV`、`DATABASE_URL`、`EMBEDDING_*` 等字段，实例化 `LLMServiceConfig()` 时会报 extra-forbidden。
- `create_app()` 和 `python -m llm_service` 都依赖默认构造配置，因此在当前仓库环境下默认启动不稳。
- 我本地执行 `python -m pytest llm_service/tests -q` 时，`test_config_defaults` 与 `test_fastapi_app_creates` 已稳定复现该问题；其余大量 async 用例还叠加了当前机器 `tmp_path` 权限错误，无法作为通过证明。
- 代码位置：
  - `llm_service/config.py:25`
  - `llm_service/main.py:23`
  - `llm_service/__main__.py:6`
- 相关文件：
  - `.env.example`

### P2. `request_id` 契约未落地，跨调用方追踪字段缺失

- 任务 briefing 明确要求支持 `request_id`，数据库 schema 也为 `agent_llm_tasks.request_id` 预留了列。
- 但 `TaskSubmitRequest` 没有 `request_id` 字段，`LLMService.submit()` / `TaskManager.submit()` 也不接收、不写入该字段。
- 这会导致 Mining / Serving 无法把上游请求链路和 runtime task 做稳定关联，削弱跨系统可追踪性。
- 代码位置：
  - `llm_service/models.py:12`
  - `llm_service/runtime/service.py:37`
  - `llm_service/runtime/task_manager.py:30`
- 契约位置：
  - `docs/messages/TASK-20260421-v11-agent-llm-runtime.md:37`
  - `databases/agent_llm_runtime/schemas/001_agent_llm_runtime.sqlite.sql:31`

## 测试缺口

- 当前未看到覆盖 `execute` 超时后的 task / attempt 一致性测试。
- 当前未看到覆盖模板 API、模板页面、模板展开执行链的测试；因为对应功能本身未交付。
- 当前未看到覆盖后台 worker / lease recovery 的端到端测试；handoff 也承认这部分未完成。
- 我尝试执行 `pytest llm_service/tests -q` 与定向测试，但当前环境的 `tmp_path` 创建权限存在 `WinError 5`，无法在此机上复核完整异步用例；因此不能接受 handoff 中“62 个测试全部通过”作为本轮唯一验证依据。

## 回归风险

- 若 Mining 按 plan 接入异步 `/tasks` 批量提交，任务会长期停留在 `queued`，批处理链路无法真正运行。
- 若 Serving 依赖模板能力统一 prompt 管理，当前 runtime 无法提供模板展开和版本化执行。
- 若上线后出现 provider 超时，task/attempt 状态可能分裂，审计、重试与问题定位都会失真。
- 若在当前仓库环境中直接启动服务，配置加载失败会导致服务无法启动或测试基线不稳定。

## 建议修复项

1. 先修正 `execute` 超时语义，保证 task/attempt/event 在超时与取消路径上的状态一致，并补齐对应测试。
2. 明确 v1 交付边界：
   - 若保留“异步 runtime”承诺，就补齐应用内 worker / recovery 闭环。
   - 若暂不支持，就下调 plan/README/handoff 描述，避免 Mining/Serving 按错误能力接入。
3. 要么把 template 平台真正接入主执行链和 API/页面，要么从本轮交付声明里去掉“完整模板管理”表述。
4. 调整 `LLMServiceConfig` 的 `.env` 读取策略或 `extra` 策略，确保在当前仓库环境下默认可启动。
5. 补齐 `request_id` 字段的 API、service、task_manager 落库与读取链路。

## 无法确认的残余风险

- 未能在当前环境完成全部 async pytest 复跑，原因是本机 `tmp_path` / pytest 临时目录权限错误；因此对某些已声明通过的测试，只能基于代码与测试文件静态审查。
- 未验证真实 DeepSeek 端到端调用，因为当前审查重点是运行时抽象与仓库内契约，不是在线 provider 可达性。

## 管理员介入影响

- 管理员已明确 LLM Runtime 必须作为独立服务，与 Mining / Serving 私有调用体系分离。
- 本次审查结论受该边界直接影响：凡是仍要求调用方自行构造 prompt、依赖外部 worker、缺失追踪字段的部分，都按“独立 runtime 底座未完成”处理。

## 最终评估

- 当前实现已经搭出了独立 LLM Runtime 的基本骨架：独立 FastAPI 进程、独立 SQLite 库、task/request/attempt/result/event 五段链路方向正确。
- 但本轮交付尚未达到“可被 Mining 与 Serving 共同依赖的稳定 runtime 底座”标准。
- 结论：**存在需要 Claude 修复的实质问题，当前不建议以 handoff 所述“完整 14 Task 已完成”作为闭环结论。**
