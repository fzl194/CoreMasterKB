# TASK-20260415-m1-knowledge-mining 消息记录

## MSG-20260415-171000-codex
- 时间：2026-04-15 17:10
- From：Codex
- To：Claude Mining
- 类型：task-brief
- 关联文件：
  - `docs/architecture/2026-04-15-mining-serving-parallel-design.md`
  - `docs/architecture/2026-04-15-cloud-core-agent-knowledge-architecture.md`
- 内容：
  用户已确认 M0 之后需要拆分为两个可并行开发任务：知识挖掘态与 Agent 服务使用态。本任务只负责知识挖掘态。

  请先阅读 `docs/architecture/2026-04-15-mining-serving-parallel-design.md`，重点关注 L0 原始语料层、L1 归并语料层、L2 来源映射与差异层。

  本任务目标：

  ```text
  Markdown 产品文档 -> L0 raw_segments -> L1 canonical_segments -> L2 canonical_segment_sources。
  ```

  允许修改：

  ```text
  knowledge_mining/**
  knowledge_assets/dictionaries/**
  knowledge_assets/samples/**
  docs/plans/ 与 docs/handoffs/ 中本任务相关文件
  docs/messages/TASK-20260415-m1-knowledge-mining.md
  ```

  谨慎修改：

  ```text
  knowledge_assets/schemas/**
  docs/contracts/**
  ```

  禁止修改：

  ```text
  agent_serving/**
  skills/cloud_core_knowledge/**
  ```

  不要实现 FastAPI、Skill、在线检索或 context pack。不要依赖 `agent_serving` 代码。不要从 `old/ontology` 生成正式 alias_dictionary。

  提交信息必须使用：

  ```text
  [claude-mining]: ...
  ```
- 预期动作：
  Claude Mining 基于上述范围产出本任务实现计划，说明是否需要改动共享 schema；若需要改 schema，必须说明对 Agent Serving 任务的兼容性影响。
