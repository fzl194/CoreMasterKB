# M1 Agent Serving 设计审查

> 日期：2026-04-16  
> 审查人：Codex  
> 任务：TASK-20260415-m1-agent-serving  
> 审查对象：
> - `docs/plans/2026-04-15-m1-agent-serving-design.md`
> - `docs/plans/2026-04-15-m1-agent-serving-impl-plan.md`
> - `knowledge_assets/schemas/001_asset_core.sql`
> - `knowledge_assets/schemas/README.md`
> - `docs/messages/TASK-20260415-m1-agent-serving.md`

## 审查背景

Claude Serving 提交了 M1 Agent Serving 设计方案，目标是实现：

```text
Agent/Skill 请求 -> 查询约束识别 -> 检索 L1 canonical_segments -> 通过 L2 选择 L0 raw_segments -> 返回 context pack。
```

本轮审查重点核对该方案是否符合 M1 共享资产契约 v0.3、是否保持 Serving 与 Mining 的边界隔离、以及实施计划是否能验证真实运行路径。

## 审查范围

本次只审查设计与实施计划，不审查尚未实现的 Claude Serving 代码。

重点核对：

- 是否只读唯一 active publish version。
- 是否以 `knowledge_assets/schemas/001_asset_core.sql` 为唯一资产表契约。
- 是否通过 `canonical_segments -> canonical_segment_sources -> raw_segments -> raw_documents` 完成 L1/L2/L0 下钻。
- 是否避免 Serving 私有维护 asset DDL。
- API、Repository、测试计划是否覆盖核心行为和错误路径。

## 发现的问题

### P1：测试 fixture 私自重建 asset DDL，绕开了唯一 schema 契约

`docs/messages/TASK-20260415-m1-agent-serving.md` 已明确要求 fixture 只能插入数据，不应重新定义表结构，并要求计划直接引用 `knowledge_assets/schemas/001_asset_core.sql`。但实施计划在 `docs/plans/2026-04-15-m1-agent-serving-impl-plan.md:268` 起手写了完整 `SCHEMA_SQL`，并使用 `asset_publish_versions`、`asset_raw_documents`、`asset_raw_segments`、`asset_canonical_segments`、`asset_canonical_segment_sources` 等 SQLite 私有表名。

这会导致两个直接风险：

- 测试通过不代表代码符合正式 `asset.*` schema，schema 漂移不会被发现。
- Mining 按正式契约写入的数据，Serving 的 Repository 可能在真实环境里读不到。

正式契约在 `knowledge_assets/schemas/README.md:9` 定义 `knowledge_assets/schemas/` 是 Mining 和 Serving 的唯一数据库契约来源；`knowledge_assets/schemas/README.md:64` 要求资产查询都带 active `publish_version_id`。测试应从共享 schema 转换/加载，或至少由统一 schema adapter 生成 SQLite 兼容 DDL，不能在 `agent_serving/tests/conftest.py` 维护第二份表结构。

建议修复：

- 删除 `conftest.py` 中手写的 asset DDL。
- 增加测试辅助函数，从 `knowledge_assets/schemas/001_asset_core.sql` 生成 SQLite 测试库，或在共享 schema 目录维护一份受控的 SQLite dev DDL。
- fixture 只负责插入 active publish version 与 L0/L1/L2 seed 数据。

### P1：API 启动路径只打开空 SQLite 文件，不能完成 M1 查询闭环

实施计划中的 `main.py` 在 `docs/plans/2026-04-15-m1-agent-serving-impl-plan.md:1465` 起只创建 `.dev/agent_kb.sqlite` 连接并注入 `AssetRepository`，没有执行 schema 初始化、没有加载 seed 数据、也没有校验 active publish version 是否存在。Task 11 的 smoke test 只请求 `/health`，见 `docs/plans/2026-04-15-m1-agent-serving-impl-plan.md:1633`，不会覆盖 `/api/v1/search` 或 `/api/v1/command/usage` 的真实启动路径。

结果是：开发者按计划启动服务后，`/health` 可用，但第一次实际查询很可能因为表不存在或没有 active 版本而返回空结果/500。这与 M1 “在线使用态最小闭环”不一致。

建议修复：

- 明确 dev mode 数据库来源：要么由 Mining/脚本预置 SQLite asset snapshot，要么由测试/开发脚本显式初始化。
- 服务启动时应检查 active publish version，不存在时给出可诊断错误或健康检查降级状态。
- Smoke test 至少增加一次已知 seed 数据下的 `/api/v1/search` 或 `/api/v1/command/usage` 请求。

### P1：冲突候选流只写在设计中，实施计划没有实现或测试

设计文档在 `docs/plans/2026-04-15-m1-agent-serving-design.md:115` 明确要求命中 `conflict_candidate` 类型 L2 时不强行回答，而是返回冲突来源并提示确认约束。但实施计划的 `drill_down` 只把 `relation_type` 查出，见 `docs/plans/2026-04-15-m1-agent-serving-impl-plan.md:571`，`ContextAssembler` 没有根据 `relation_type == "conflict_candidate"` 构造冲突不确定性，见 `docs/plans/2026-04-15-m1-agent-serving-impl-plan.md:1049`；测试 seed 也没有覆盖 conflict candidate。

这会让系统在存在冲突映射时仍按普通 raw segment 返回，违背 M1 对差异下钻的关键边界。

建议修复：

- 在 seed 数据中加入至少一条 `conflict_candidate`。
- 在 Resolver/Assembler 中把 conflict candidate 转换为 uncertainty/conflict source，而不是普通答案材料。
- 增加 API 级测试，断言冲突情况下不会输出强确定答案。

### P2：serving.retrieval_logs 设计、测试和 Repository 表名不一致，且 API 没有写日志

设计文档声明 `LogRepository` 写入 `serving.retrieval_logs`，见 `docs/plans/2026-04-15-m1-agent-serving-design.md:64`；Serving schema 也创建 `serving.retrieval_logs`，见 `docs/plans/2026-04-15-m1-agent-serving-impl-plan.md:1137`。但 LogRepository 测试和实现使用的是 `serving_retrieval_logs`，见 `docs/plans/2026-04-15-m1-agent-serving-impl-plan.md:1185` 和 `docs/plans/2026-04-15-m1-agent-serving-impl-plan.md:1272`。

此外，API 路由没有调用 `LogRepository`，所以即使日志表存在，也不会记录检索请求。

建议修复：

- 统一 PostgreSQL 与 SQLite dev mode 的 serving schema 映射策略。
- 如果 M1 要保留 retrieval log，API 路径应注入并调用 `LogRepository`，并增加 API 测试验证日志落库。
- 如果 M1 暂不写日志，应从本轮文件清单和实施任务中移除，避免伪完成。

### P2：文件清单与实施任务不一致，容易造成交付缺口

设计文档列出了 `SearchPlanner` 和 `context_assemble.py`，见 `docs/plans/2026-04-15-m1-agent-serving-design.md:66` 与 `docs/plans/2026-04-15-m1-agent-serving-design.md:71`。但实施计划没有实现 Planner，也没有实现 `/api/v1/context/assemble`。这不一定是架构错误，但当前文档没有说明它们被延期或合并到其他模块。

建议修复：

- 若 Planner 和 context assemble 不是 M1 必需项，从设计文件清单中删去或标注 M2+。
- 若它们属于 M1 范围，补齐实现任务和测试。

## 测试缺口

- 缺少基于正式 schema 契约的测试，当前计划会用私有 DDL 掩盖 schema drift。
- 缺少真实服务启动后的查询 smoke test。
- 缺少 active publish version 不存在、多个 active 异常、空库等错误路径测试。
- 缺少 `conflict_candidate` 行为测试。
- 缺少 retrieval log 的 API 集成测试。

## 回归风险

- 如果按当前计划实施，Mining 与 Serving 很可能各自测试通过，但实际数据库对接失败。
- `/health` 通过会掩盖查询 API 无法工作的运行时问题。
- 冲突候选被当作普通答案返回，会降低 Agent 回答的可信度，尤其是跨产品/跨版本命令参考。

## 建议修复项

1. 先修订实施计划，移除 Serving 私有 asset DDL，改为引用共享 schema 或受控 schema adapter。
2. 明确 dev SQLite 初始化与数据来源，增加查询级 smoke test。
3. 补齐 conflict candidate 的 Resolver/Assembler 行为和测试。
4. 统一 retrieval log 表名，并决定 M1 是否实际写日志。
5. 同步设计文档与实施计划的文件清单，避免 Planner/context assemble 名义上在范围内、实现中缺失。

## 无法确认的残余风险

- 尚未看到 Claude Serving 的实际代码提交，无法确认其最终实现是否会偏离当前计划。
- 尚未看到 Mining 侧最终写库实现，无法用真实数据验证 Serving Repository 的 SQL 兼容性。
- 当前审查未运行新测试，因为本轮对象是设计与实施计划。

## 管理员介入影响

管理员已要求 Mining 与 Serving 独立并行开发，并以 `knowledge_assets/schemas/` 作为唯一数据库桥梁。当前审查结论延续该边界：Serving 不能通过私有 DDL 规避共享契约，也不能在测试中维护第二套 asset 表语义。

## 最终评估

核心方向可接受：纯 SQL 检索 L1、通过 L2 下钻 L0、不引入 vector、Serving 不写 asset 表，符合 M1 阶段定位。

但当前实施计划不建议直接开工。至少需要先修复 P1 项：测试必须绑定正式 schema 契约，服务启动路径必须能完成查询级闭环，冲突候选必须按不确定性处理。完成这些修订后，可以进入实现阶段。
