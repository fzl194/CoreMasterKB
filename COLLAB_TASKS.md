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

## TASK-20260415-cloud-core-architecture
- 标题：云核心网 Agent Knowledge Backend 总体架构与 Phase 1A 落地设计
- 级别：正式
- 状态：Claude 已完成 M0 实现，待 Codex 审查
- 当前阶段：M0 实现完成，等待 Codex 审查
- Claude：已完成 M0 全部 9 个 Task（T1-T9），验证通过，handoff 已产出
- Codex：已完成 M0 审查，发现 package discovery 为空和架构基线残留旧 M0 说明，需 Claude 修复后回交
- 管理员：用户已确认 Agent / Skill / Serving / Assets / Mining 分层架构
- 计划文档：
  - `docs/plans/2026-04-15-m0-skeleton-design.md`（M0 设计文档）
  - `docs/plans/2026-04-15-m0-skeleton.md`（M0 实现计划）
- 交接文档：`docs/handoffs/2026-04-15-m0-claude-handoff.md`
- 审查文档：`docs/analysis/2026-04-15-m0-skeleton-codex-review.md`
- 修复文档：
- 管理员文档：
- 最新消息序号：MSG-20260415-165500-codex
- 备注：架构文档为 `docs/architecture/2026-04-15-cloud-core-agent-knowledge-architecture.md`；旧代码仅作为 `old/` 参考，不作为新系统 import 依赖。

## 已完成任务

### 说明

- 可将已闭环任务移动到此区
- 如任务较多，可后续按月份拆分归档
