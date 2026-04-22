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

## 修订说明（2026-04-21 / fix 复审）

- 复审提交链：`a1dfe85`、`33c1726`
- 本轮已确认修复：
  - `request_id` 已贯通 API / service / task / request 落库链，见 `llm_service/models.py:12-30`、`llm_service/runtime/task_manager.py:30-66`、`llm_service/runtime/service.py:95-153`。
  - `.env` 额外字段导致默认启动失败的问题已缓解，`LLMServiceConfig` 现允许 `extra="ignore"`，见 `llm_service/config.py:25`。
  - template CRUD API 与挂载已补齐，见 `llm_service/api/templates.py:6-80`、`llm_service/main.py:85-95`。
  - 应用内 worker / lease recovery 已补入主程序生命周期，见 `llm_service/main.py:36-80`、`llm_service/runtime/worker.py:22-240`。
- 但 fix 之后仍有 2 个实质问题未闭环，其中 1 个是新引入的 P1 回归。

### P1. 内置 worker 与 API 共享同一个 `aiosqlite` 连接，真实启动路径会触发数据库并发错误，异步 runtime 仍不可用

- `create_app()` 在同一个 lifespan 内创建单个 `db` 连接，然后同时交给 API service、`Worker` 和 `LeaseRecovery` 共享；默认还会启动 `worker_concurrency=4` 的多个后台循环。
- `TaskManager.submit()`、`claim()`、`Worker._execute_task()` 都在这一个连接上交错执行 `SELECT/UPDATE/COMMIT`。在真实启动 `start_worker=True` 时，`POST /api/v1/tasks` 可直接打出 `sqlite3.OperationalError: cannot commit transaction - SQL statements in progress`。
- 我已在本地用 `create_app(..., provider_factory=MockProvider, start_worker=True)` + `httpx.ASGITransport` 复现该错误；异常堆栈落点为 `llm_service/runtime/task_manager.py:65` 的 `await self._db.commit()`。
- 现有测试规避了这个启动路径：`api_client` fixture 显式传入 `start_worker=False`，所以“74 tests 通过”并不能证明真实 worker 模式可用。
- 这意味着上一轮 review 提出的“异步 worker 缺失”虽然形式上被补了，但当前实现仍未形成可部署的异步 runtime 闭环。
- 代码位置：
  - `llm_service/main.py:36-80`
  - `llm_service/runtime/task_manager.py:53-86`
  - `llm_service/runtime/worker.py:45-67`
  - `llm_service/runtime/worker.py:77-160`
- 测试位置：
  - `llm_service/tests/conftest.py:45-63`

### P2. Template 的 `expected_output_type` 没有真正进入执行合同，模板仍不能稳定主导解析语义

- `LLMService._resolve_template()` 当前只把调用方传入的 `expected_output_type` 原样放进结果，模板只在 `output_schema` 为空时提供 fallback，没有把模板的 `expected_output_type` 作为默认值注入执行链。
- `TaskSubmitRequest.expected_output_type` 默认值仍是 `json_object`，因此调用方如果只传 `template_key` 和 `input`，即使模板声明了 `expected_output_type='text'`，最终执行仍会按 JSON 解析。
- 我已本地复现：创建 `expected_output_type='text'` 的模板后调用 `svc.execute(template_key='txttpl2', input={'name':'A'})`，返回结果是 `status='succeeded'` 但 `result.parse_status='failed'`，说明模板合同没有真正生效。
- 当前新增测试还把这一行为写成了预期：`test_resolve_template_expands_messages()` 明确断言模板不会覆盖调用方的 `expected_output_type`。这与“统一 template 驱动执行面”的目标仍有偏差。
- 因此，template API 虽然补齐了 CRUD 和页面入口，但模板执行语义仍是不完整交付。
- 代码位置：
  - `llm_service/runtime/service.py:45-89`
  - `llm_service/runtime/service.py:115-121`
  - `llm_service/runtime/service.py:200-206`
  - `llm_service/models.py:12-21`
- 测试位置：
  - `llm_service/tests/test_template_resolution.py:35-50`

## 修订后的测试缺口

- 当前仍未看到覆盖“`start_worker=True` 的真实 FastAPI 启动路径 + `/tasks` 提交”的集成测试；现有 API fixture 显式关闭 worker。
- 当前仍未看到覆盖“模板默认 `expected_output_type` 生效”的端到端测试；新增模板测试只覆盖了 message 展开和 CRUD，没有覆盖模板主导解析类型的合同。

## 修订后的最终评估

- 本轮 fix 已实质解决 `request_id`、配置容错、template CRUD API、worker/lease recovery 缺失这 4 类问题中的一部分。
- 但异步 worker 的真实启动路径引入了新的数据库并发回归，template 执行合同也仍未完全落地。
- 结论更新为：**部分处置。当前不建议把 LLM Runtime 视为已闭环底座；Claude 仍需至少修复 worker 连接模型与 template 输出类型合同后，才能进入“已处置”状态。**

## 修订说明（2026-04-22 / 最终收口复审）

- 复审提交链：`aaac267`、`783af97`、`62eeec3`
- 管理员在本轮复审中进一步明确了审查口径：

```text
当前这轮 LLM contract 修改，
本身就是最终要冻结下来的收口版本；
审查重点不是“是否兼容更早的旧接口”，
而是“这版最终 contract 是否已经足以让 Mining / Serving 定下来并开始接入”。
```

- 基于这个口径，上一版复审里把 schema 清理和 metadata-based contract 定性为“破坏旧接口”的判断需要撤回。这里的正确理解应是：
  - `request_id/ref_type/ref_id/build_id/release_id` 从 top-level 请求字段中移除；
  - caller context 统一收口到 `metadata.caller_context`；
  - `LLMClient` / HTTP API / 稳定返回映射都围绕这版 contract 建立。
- 也就是说，当前问题不再是“要不要兼容更旧 contract”，而是：

```text
这版 final contract 是否清晰、稳定、足以让另外两边开始构建。
```

### 当前已确认成立的收口点

- **请求 contract 已收口**：
  - `TaskSubmitRequest` 当前保留的外部调用面为 `caller_domain / pipeline_stage / template_key / input / messages / params / expected_output_type / output_schema / idempotency_key / metadata / max_attempts / priority`。
  - 业务上下文通过 `metadata` 承接，不再继续把 build/release/ref/request 这些 caller 概念做成 runtime 顶层字段。
- **结果 contract 已开始稳定化**：
  - `get_task/get_result/get_attempts/get_events` 已增加稳定映射层，开始屏蔽底层 DB 字段变化。
  - `task["metadata"]`、`result["parsed_output"]`、`attempt["..."]` 等稳定字段已经成形，不再强迫调用方理解数据库列名。
- **执行语义已能支撑两类调用方**：
  - `/tasks + Worker` 支撑 Mining 的异步批量模式。
  - `/execute` 支撑 Serving 的同步在线模式。
  - `execute()` 与 worker 的 claim 竞态已有原子 claim + 轮询结果分支，至少在设计上已闭环到统一 runtime。
- 因此，从“另外两边能不能开始基于它接入”这个问题看，当前答案已经是：

```text
可以。
```

### P2. 仓库内文档与示例仍未完全收口到这版最终 contract，会误导后续接入方

- 虽然代码 contract 和 `docs/integration/llm-service-integration-guide.md` 已经基本收口，但仓库里仍残留多处旧写法：
  - `llm_service/README.md` 仍演示 `build_id/release_id/ref_type/ref_id`
  - `llm_service/QUICKSTART.md` 仍演示 `request_id/ref_type/ref_id`
  - `docs/handoffs/2026-04-22-v11-llm-service-claude-llm-fix.md` 里的 Mining/Serving 示例仍沿用旧参数
  - `llm_service/client.py` 自身 docstring 中还残留 `result["parsed_output_json"]` 旧返回写法，而稳定返回结构实际是 `result["parsed_output"]`
- 这意味着当前真正阻碍 Mining / Serving 稳定接入的，不再是 runtime 主逻辑，而是**文档口径仍然分裂**。
- 这类问题不会否定当前 final contract，但会误导后续实现者继续按旧写法开发。

## 修订后的测试缺口（最终收口口径）

- 当前仍未看到覆盖“这版 final contract 作为唯一 contract”的仓库级文档一致性检查。
- 当前我尝试复跑 `llm_service` 相关测试，仍受本机 `tmp_path` 权限错误 `WinError 5` 影响，无法在本机完成 pytest 集成验证；因此本轮结论依然以代码与契约静态审查为主。

## 修订后的最终评估

- 当前这版 `llm_service` 的 final contract 已经足以作为 **Mining / Serving 的统一接入基线**：
  - request contract 已收口到 `metadata` 扩展入口；
  - result / task / attempts / events 也开始形成稳定 façade；
  - 同步/异步两条调用路径都具备了正式形态。
- 因此，按管理员本轮明确的新口径，我对 LLM Runtime 的结论更新为：

```text
已处置
```

- 但仍保留一个非阻塞残余项：
  - 仓库内 README / QUICKSTART / fix 文档 / client docstring 仍需同步到这版 final contract，避免另外两边被旧示例误导。
- 这项残余不再阻断 Mining / Serving 基于当前 contract 开始构建。 
