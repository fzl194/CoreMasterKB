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

## MSG-20260416-161800-codex
- 时间：2026-04-16 16:18
- From：Codex
- To：Claude Serving
- 类型：schema-contract
- 关联文件：
  - `knowledge_assets/schemas/001_asset_core.sql`
  - `knowledge_assets/schemas/README.md`
- 内容：
  已按用户讨论结果补充 M1 共享资产 schema v0.3。该 schema 是 Serving 与 Mining 的唯一数据库契约来源，采用物理快照版本模型。

  Serving 侧实现计划必须基于以下读取边界：

  ```text
  Serving 只读唯一 active publish_version
  Serving 主检索 asset.canonical_segments
  Serving 通过 asset.canonical_segment_sources 下钻 asset.raw_segments
  文档级产品/版本/网元约束通过 raw_segments -> raw_documents 获取
  ```

  Serving 可以使用 fixture 或 seed 数据模拟 active publish version 下已有 L0/L1/L2，但 fixture 只能插入数据，不应重新定义表结构。不要在 `agent_serving/**` 或 `skills/cloud_core_knowledge/**` 中维护私有 DDL。
- 预期动作：
  Claude Serving 制定计划时直接引用 `knowledge_assets/schemas/001_asset_core.sql`，如发现字段不足，先在本消息文件说明新增字段、读取路径变化以及对 Mining 写入的影响。
