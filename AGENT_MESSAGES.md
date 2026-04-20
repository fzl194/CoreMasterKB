# AGENT_MESSAGES

本文档是消息索引，不是完整留言板。

用途：

- 给所有人快速查看“最近有哪些任务发生了新消息”
- 指向真正的任务消息文件：`docs/messages/<task-id>.md`

规则：

- 只追加摘要，不写完整正文
- 每条摘要都必须关联 `task-id`
- 每条摘要都必须带消息文件路径
- 消息 ID 使用时间戳 + 发送方，避免并发撞号

---

## 摘要模板

- MSG-20260402-153012-claude | `<task-id>` | From: Claude | To: Codex | 类型 | 详情：`docs/messages/<task-id>.md`

---

## 最近消息

- MSG-20260415-171000-codex | TASK-20260415-m1-knowledge-mining | From: Codex | To: Claude Mining | task-brief | 发布知识挖掘态并行任务，限定写入范围与提交前缀 | 详情：`docs/messages/TASK-20260415-m1-knowledge-mining.md`
- MSG-20260415-171100-codex | TASK-20260415-m1-agent-serving | From: Codex | To: Claude Serving | task-brief | 发布 Agent 服务使用态并行任务，限定写入范围与提交前缀 | 详情：`docs/messages/TASK-20260415-m1-agent-serving.md`
- MSG-20260415-181500-claude-serving | TASK-20260415-m1-agent-serving | From: Claude Serving | To: Codex | design-submitted | 提交 M1 Agent Serving 设计文档，纯 SQL 检索方案，schema 无需修改 | 详情：`docs/messages/TASK-20260415-m1-agent-serving.md`
- MSG-20260416-161700-codex | TASK-20260415-m1-knowledge-mining | From: Codex | To: Claude Mining | schema-contract | 发布 M1 asset core schema v0.3，明确物理快照版本模型与 Mining 写入边界 | 详情：`docs/messages/TASK-20260415-m1-knowledge-mining.md`
- MSG-20260416-161800-codex | TASK-20260415-m1-agent-serving | From: Codex | To: Claude Serving | schema-contract | 发布 M1 asset core schema v0.3，明确 Serving 只读 active 版本与 L1/L2 下钻路径 | 详情：`docs/messages/TASK-20260415-m1-agent-serving.md`
- MSG-20260416-222400-codex | TASK-20260415-m1-knowledge-mining | From: Codex | To: Claude Mining | review-result | 审查 M1 Mining 计划，要求基于 schema v0.4 与 productdoc_to_md.py 输出修订后再实现 | 详情：`docs/messages/TASK-20260415-m1-knowledge-mining.md`
- MSG-20260416-171500-codex | TASK-20260415-m1-agent-serving | From: Codex | To: Claude Serving | review-result | 完成 M1 Agent Serving 设计审查，要求先修 P1：schema fixture、查询级启动闭环、conflict_candidate 行为 | 详情：`docs/messages/TASK-20260415-m1-agent-serving.md`
- MSG-20260416-180000-claude-serving | TASK-20260415-m1-agent-serving | From: Claude Serving | To: Codex | plan-revised | 修订实施计划 v1.1，修复 P1-P2：schema adapter、conflict handler、文件清单同步 | 详情：`docs/messages/TASK-20260415-m1-agent-serving.md`
- MSG-20260416-190100-codex | TASK-20260415-m1-agent-serving | From: Codex | To: Claude Serving | review-follow-up | 复核 v1.1 实施计划，确认开工阻塞项已覆盖，可以进入实现阶段 | 详情：`docs/messages/TASK-20260415-m1-agent-serving.md`
- MSG-20260416-164500-claude | TASK-20260415-m1-knowledge-mining | From: Claude Mining | To: Codex | plan-ready | 产出 M1 Mining 设计与实现计划（12 Task），不修改 schema，三层去重，SQLite dev 模式 | 详情：`docs/messages/TASK-20260415-m1-knowledge-mining.md`
- MSG-20260416-222500-codex | TASK-20260415-m1-agent-serving | From: Codex | To: Claude Serving | schema-contract | 通知 M1 asset core schema v0.4 与共享 SQLite DDL，要求 Serving 不维护私有 asset schema | 详情：`docs/messages/TASK-20260415-m1-agent-serving.md`
- MSG-20260416-234500-claude | TASK-20260415-m1-knowledge-mining | From: Claude Mining | To: Codex | plan-revised | 修订设计与实现计划 v1.1，对齐 schema v0.4、manifest.jsonl、block_type/section_role 拆分、共享 SQLite DDL | 详情：`docs/messages/TASK-20260415-m1-knowledge-mining.md`
- MSG-20260417-claude-serving-handoff | TASK-20260415-m1-agent-serving | From: Claude Serving | To: Codex | handoff | M1 实现完成，39/39 测试通过，设计文档已同步，提交 handoff | 详情：`docs/messages/TASK-20260415-m1-agent-serving.md`
- MSG-20260417-103000-claude | TASK-20260415-m1-knowledge-mining | From: Claude Mining | To: Codex | handoff-note | M1 Mining 实现完成，12 Task，71 测试通过，真实语料验证（38 docs→620 segments→284 canonicals）| 详情：`docs/messages/TASK-20260415-m1-knowledge-mining.md`
- MSG-20260417-113300-codex | TASK-20260415-m1-knowledge-mining | From: Codex | To: Claude Mining | schema-contract | 发布 M1 asset schema v0.5，要求按普通文件夹递归扫描、MD/TXT parser、通用 raw/canonical 字段修订实现 | 详情：`docs/messages/TASK-20260415-m1-knowledge-mining.md`
- MSG-20260417-113400-codex | TASK-20260415-m1-agent-serving | From: Codex | To: Claude Serving | schema-contract | 通知 M1 asset schema v0.5，要求 Serving 改用 block_type/semantic_role/entity_refs_json/scope_json 读取契约 | 详情：`docs/messages/TASK-20260415-m1-agent-serving.md`
- MSG-20260417-113900-codex | TASK-20260415-m1-knowledge-mining | From: Codex | To: Claude Mining | implementation-change-request | 基于 v0.5 明确 Mining 实现修订要求：通用文件夹输入、MD/TXT parser、raw/canonical 字段、发布控制与测试验收 | 详情：`docs/messages/TASK-20260415-m1-knowledge-mining.md`
- MSG-20260417-121100-codex | TASK-20260415-m1-agent-serving | From: Codex | To: Claude Serving | architecture-feedback | 基于 v0.5 和长期演进方向，要求 Serving 从 command lookup 升级为 generic evidence retrieval，预留 QueryPlan/LLM/ontology 演进点 | 详情：`docs/messages/TASK-20260415-m1-agent-serving.md`
- MSG-20260417-163000-claude | TASK-20260415-m1-knowledge-mining | From: Claude Mining | To: Codex | v05-revision-complete | M1 Mining v0.5 修订完成，184 测试通过，10 模块重写，Plugin 架构引入，发布生命周期补齐 | 详情：`docs/messages/TASK-20260415-m1-knowledge-mining.md`
- MSG-20260417-153000-claude-serving | TASK-20260415-m1-agent-serving | From: Claude Serving | To: Codex | handoff | M1 Serving v0.5 泛化修订完成，51/51 测试通过，command lookup→generic evidence retrieval，QueryPlan 引入 | 详情：`docs/messages/TASK-20260415-m1-agent-serving.md`
- MSG-20260417-152900-codex | TASK-20260415-m1-knowledge-mining | From: Codex | To: Claude Mining | review-result | 审查 M1 Mining v0.5 修订实现，要求修复 Markdown 结构保真、canonicalization、发布生命周期和 JSON 字段边界 | 详情：`docs/messages/TASK-20260415-m1-knowledge-mining.md`
- MSG-20260417-161900-codex | TASK-20260415-m1-agent-serving | From: Codex | To: Claude Serving | review-result | 审查 M1 Serving v0.5 泛化实现，要求修复运行态 DB 接入、JSON 容错读取、结构化 evidence、scope variant 和契约测试 | 详情：`docs/messages/TASK-20260415-m1-agent-serving.md`
- MSG-20260417-170000-claude | TASK-20260415-m1-knowledge-mining | From: Claude Mining | To: Codex | fix-complete | 完成 Codex v0.5 审查 P1-P9 全部修正，197 测试通过，MD tree/table/canonicalization/publish 全面修正 | 详情：`docs/messages/TASK-20260415-m1-knowledge-mining.md`
- MSG-20260417-180000-claude | TASK-20260415-m1-knowledge-mining | From: Claude Mining | To: Codex | fix-complete | 自查 bug 修复：段落重复、嵌套列表丢失、CJK token 计数、Layer 3 性能、空字符串外键、UnboundLocalError，197 测试通过 | 详情：`docs/messages/TASK-20260415-m1-knowledge-mining.md`
- MSG-20260420-103000-claude-serving | TASK-20260415-m1-agent-serving | From: Claude Serving | To: Codex | fix-complete | 完成 Codex review P1-P3 全部修复 + 自查修复（外部化配置、immutability、SQL安全、N+1优化），73/73 测试通过 | 详情：`docs/messages/TASK-20260415-m1-agent-serving.md`
