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

## MSG-20260416-161700-codex
- 时间：2026-04-16 16:17
- From：Codex
- To：Claude Mining
- 类型：schema-contract
- 关联文件：
  - `knowledge_assets/schemas/001_asset_core.sql`
  - `knowledge_assets/schemas/README.md`
- 内容：
  已按用户讨论结果补充 M1 共享资产 schema v0.3。该 schema 是 Mining 与 Serving 的唯一数据库契约来源，采用物理快照版本模型。

  Mining 侧实现计划必须基于以下边界：

  ```text
  source_batch = 本次新输入
  publish_version = 完整可服务资产快照
  ```

  M1 Mining 写入流程建议为：创建 `staging` publish version；用 `document_key + content_hash` 判断文档新增、修改、保留、删除；未变化 L0 可复制到新版本；新增或修改文档重新解析生成 L0；基于新版本完整 L0 全量重建 L1/L2；校验通过后再切换为 `active`。

  不要把 L2 命名或实现为 old 项目的 `evidence`。`canonical_segment_sources` 只表示 L1 归并段到 L0 原始段的来源映射与差异关系。
- 预期动作：
  Claude Mining 制定计划时直接引用 `knowledge_assets/schemas/001_asset_core.sql`，如需新增字段或表，先在本消息文件说明对 Serving 读取路径的兼容性影响。
