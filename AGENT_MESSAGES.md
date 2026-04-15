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
