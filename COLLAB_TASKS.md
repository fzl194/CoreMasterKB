# COLLAB_TASKS

本文档是仓库内协作任务总入口。

使用规则：

- 每个非琐碎任务只保留一条任务记录
- 所有正式文档路径都挂到对应任务下
- 当前状态、当前阶段、最新消息序号优先在这里维护
- 已结束任务可移动到“已完成任务”区，但不要删除历史

---

## 活跃任务模板

## <task-id>
- 标题：
- 级别：
- 状态：
- 当前阶段：
- Claude：
- Codex：
- 管理员：
- 计划文档：
- 交接文档：
- 审查文档：
- 修复文档：
- 管理员文档：
- 最新消息序号：
- 备注：

字段分权：

- Claude 维护：`计划文档`、`交接文档`、`修复文档`
- Codex 维护：`审查文档`
- 管理员维护：`状态`、`当前阶段`、`备注`
- 三方都可维护：自己的责任字段、`最新消息序号`

---

## 活跃任务

## TASK-20260415-m1-knowledge-mining
- 标题：M1 Knowledge Mining / 原始语料与归并语料生产
- 级别：正式
- 状态：v0.5 审查修正 + 自查 bug 修复完成，197 测试通过，待 Codex 复审
- 当前阶段：Claude Mining 已完成 Codex v0.5 审查 P1-P9 修正 + 自查 6 项 bug 修复（段落重复、嵌套列表、CJK token、Layer 3 性能、空外键、UnboundLocalError），197 测试通过，真实语料验证通过，待 Codex 复审
- Claude：负责 `knowledge_mining/**`，提交前缀 `[claude-mining]:`，已完成 v0.5 审查修正 + 自查 bug 修复
- Codex：已定义任务边界、资产三层模型与禁止修改范围；已完成 v0.5 fix 复审，要求继续修 active 失败隔离、Markdown 跳级 heading、混合嵌套 list 等问题
- 管理员：用户要求该任务与 Agent Serving 任务独立并行开发
- 计划文档：
  - `docs/plans/2026-04-16-m1-knowledge-mining-design.md`
  - `docs/plans/2026-04-16-m1-knowledge-mining-impl-plan.md`
  - `docs/plans/2026-04-17-m1-knowledge-mining-v05-revision-plan.md`（v0.5 修订计划）
- 交接文档：
  - `docs/handoffs/2026-04-17-m1-knowledge-mining-claude-handoff.md`（v1.1 handoff）
  - `docs/handoffs/2026-04-17-m1-knowledge-mining-claude-v05-revision.md`（v0.5 修正 handoff）
- 审查文档：
  - `docs/analysis/2026-04-16-m1-knowledge-mining-plan-codex-review.md`
  - `docs/analysis/2026-04-17-m1-knowledge-mining-v05-codex-review.md`
  - `docs/analysis/2026-04-20-m1-knowledge-mining-fix-codex-review.md`
- 修复文档：
- 管理员文档：
  - `docs/architecture/2026-04-15-mining-serving-parallel-design.md`
- 最新消息序号：MSG-20260420-102000-codex
- 备注：本任务禁止修改 `agent_serving/**` 与 `skills/cloud_core_knowledge/**`；如需改共享 schema，必须先在消息中说明兼容性影响。

## TASK-20260415-m1-agent-serving
- 标题：M1 Agent Serving / 归并语料检索与差异下钻
- 级别：正式
- 状态：Codex review P1-P3 修复 + 自查修复完成，73/73 测试通过，待 Codex 复审
- 当前阶段：Claude Serving 已完成 Codex review 全部 12 项修复 + python-reviewer 自查修复（外部化配置、immutability、SQL安全、N+1优化、契约测试）
- Claude：负责 `agent_serving/**` 与 `skills/cloud_core_knowledge/**`，提交前缀 `[claude-serving]:`，Codex review 修复 + 自查修复已完成
- Codex：已定义任务边界、运行态只读约束与禁止修改范围；已完成 v0.5 fix 复审，要求继续修真实 Mining DB 召回排序、scope 维度覆盖、source audit 信息和契约测试强度
- 管理员：用户要求该任务与 Knowledge Mining 任务独立并行开发
- 计划文档：
  - `docs/plans/2026-04-15-m1-agent-serving-design.md`
  - `docs/plans/2026-04-15-m1-agent-serving-impl-plan.md`
- 交接文档：`docs/handoffs/2026-04-17-m1-agent-serving-claude-handoff.md`
- 审查文档：
  - `docs/analysis/2026-04-16-m1-agent-serving-codex-review.md`
  - `docs/analysis/2026-04-17-m1-agent-serving-v05-codex-review.md`
  - `docs/analysis/2026-04-20-m1-agent-serving-fix-codex-review.md`
- 修复文档：
- 管理员文档：
  - `docs/architecture/2026-04-15-mining-serving-parallel-design.md`
- 最新消息序号：MSG-20260420-110500-codex
- 备注：本任务禁止修改 `knowledge_mining/**` 与 `knowledge_assets/dictionaries/**`；如需改共享 schema，必须先在消息中说明兼容性影响。

## 已完成任务

### 说明

- 可将已闭环任务移动到此区
- 如任务较多，可后续按月份拆分归档

## TASK-20260415-cloud-core-architecture
- 标题：云核心网 Agent Knowledge Backend 总体架构与 Phase 1A 落地设计
- 级别：正式
- 状态：M0 已闭环；任务消息已归档
- 当前阶段：M0 已完成；M1 Mining / Serving 已拆分为独立活跃任务
- Claude：已完成 M0 全部 9 个 Task（T1-T9）与 Codex review P1-P3 修复
- Codex：已复核 M0 fix 并确认闭环；已发布 M1 Mining / Serving 并行开发上下文与任务边界
- 管理员：用户已确认 Agent / Skill / Serving / Assets / Mining 分层架构
- 计划文档：
  - `docs/archive/2026-04/TASK-20260415-cloud-core-architecture/plans/2026-04-15-m0-skeleton-design.md`（M0 设计文档）
  - `docs/archive/2026-04/TASK-20260415-cloud-core-architecture/plans/2026-04-15-m0-skeleton.md`（M0 实现计划）
- 交接文档：`docs/archive/2026-04/TASK-20260415-cloud-core-architecture/handoffs/2026-04-15-m0-claude-handoff.md`
- 审查文档：`docs/archive/2026-04/TASK-20260415-cloud-core-architecture/analysis/2026-04-15-m0-skeleton-codex-review.md`
- 修复文档：`docs/archive/2026-04/TASK-20260415-cloud-core-architecture/handoffs/2026-04-15-m0-claude-fix.md`
- 管理员文档：
- 最新消息序号：MSG-20260415-172000-codex（已归档至 `docs/archive/2026-04/TASK-20260415-cloud-core-architecture/messages/TASK-20260415-cloud-core-architecture.md`）
- 备注：架构文档为 `docs/architecture/2026-04-15-cloud-core-agent-knowledge-architecture.md`；并行开发上下文为 `docs/architecture/2026-04-15-mining-serving-parallel-design.md`，仍由后续 M1 任务原位引用，不归档。旧代码仅作为 `old/` 参考，不作为新系统 import 依赖。
