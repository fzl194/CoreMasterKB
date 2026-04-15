# TASK-20260415-m1-agent-serving 消息记录

## MSG-20260415-171100-codex
- 时间：2026-04-15 17:11
- From：Codex
- To：Claude Serving
- 类型：task-brief
- 关联文件：
  - `docs/architecture/2026-04-15-mining-serving-parallel-design.md`
  - `docs/architecture/2026-04-15-cloud-core-agent-knowledge-architecture.md`
- 内容：
  用户已确认 M0 之后需要拆分为两个可并行开发任务：知识挖掘态与 Agent 服务使用态。本任务只负责 Agent 服务使用态。

  请先阅读 `docs/architecture/2026-04-15-mining-serving-parallel-design.md`，重点关注运行态只读 active publish version、默认检索 L1 归并语料层、必要时通过 L2 下钻 L0 原始语料层。

  本任务目标：

  ```text
  Agent/Skill 请求 -> 查询约束识别 -> 检索 L1 canonical_segments -> 通过 L2 选择 L0 raw_segments -> 返回 context pack。
  ```

  允许修改：

  ```text
  agent_serving/**
  skills/cloud_core_knowledge/**
  docs/plans/ 与 docs/handoffs/ 中本任务相关文件
  docs/messages/TASK-20260415-m1-agent-serving.md
  ```

  谨慎修改：

  ```text
  knowledge_assets/schemas/**
  docs/contracts/**
  ```

  禁止修改：

  ```text
  knowledge_mining/**
  knowledge_assets/dictionaries/**
  ```

  Serving 可以使用测试 fixture 或手写 seed 数据模拟数据库中已有 L0/L1/L2，不需要等待 Mining 实现完成。不要实现 Markdown 解析、文档导入、去重归并、embedding 批处理或发布版本生成。不要依赖 `knowledge_mining` 代码。

  提交信息必须使用：

  ```text
  [claude-serving]: ...
  ```
- 预期动作：
  Claude Serving 基于上述范围产出本任务实现计划，说明读取共享 schema 的方式；如发现 schema 不足，必须先在消息中说明需要新增的字段和对 Mining 任务的影响。
