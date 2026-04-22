# LLM Service v1.1 Fix 文档

> 类型：fix
> 日期：2026-04-22
> 提交：`af28173`
> 关联 review：`docs/analysis/2026-04-21-v11-agent-llm-runtime-codex-review.md`

## 修复背景

Codex 在 fix 复审中提出 2 个未闭环问题（P1 + P2），同时我进行了深度自查，发现额外 4 CRITICAL + 7 HIGH + 9 MEDIUM 问题。

## 已修项

### Codex Review 修复

| ID | 问题 | 修复 |
|-----|------|------|
| P1 | Worker/API 共享 aiosqlite 连接导致并发 commit 冲突 | Worker、LeaseRecovery 各自使用独立 DB 连接（`main.py:62-116`） |
| P2 | Template `expected_output_type` 不进入执行合同 | 解析链改为 caller → template → "json_object" 三级 fallback |

### 自查修复

| ID | 严重度 | 问题 | 修复 |
|-----|--------|------|------|
| C1 | CRITICAL | `task_manager.fail()` fetchone 后无 null guard | 加 `if row is None: return` |
| C2 | CRITICAL | `executor.run()` 5 处 fetchone 无 null guard | 全部加 null guard |
| C3 | CRITICAL | `executor.py` 缺少 EventBus import | 补充 import |
| C4 | CRITICAL | `_resolve_template` 类型签名与实际调用不匹配 | 改为 `str \| None` |
| H1 | HIGH | `execute()` 未捕获意外异常 | 加 `except Exception` 返回结构化错误 |
| H2 | HIGH | `parse_output` 对 None raw_text 处理不当 | 加显式 None/empty guard |
| H4 | HIGH | `pipeline_stage` 无验证 | 加 `pattern=r"^[a-z][a-z0-9_]{1,63}$"` |
| H5 | HIGH | template_registry 动态 SQL 安全性不明确 | 加注释说明 allowlist 保护 |
| H7 | HIGH | lifespan 启动失败时 DB 连接泄漏 | 包裹 try/except + 显式清理 |
| M1 | MEDIUM | `_build_execute_response` JSON decode 可能崩溃 | 包裹 try/except |
| M5 | MEDIUM | `service.py` 无日志 | 加 logger |

## 未修项（后续迭代）

| ID | 严重度 | 问题 | 原因 |
|-----|--------|------|------|
| H3 | HIGH | Worker/API 共享 Provider 实例 | 当前 Provider 无状态，暂不构成实际风险 |
| H6 | HIGH | API 无 response_model | 功能正确，后续统一加强 |
| M2 | MEDIUM | caller_domain 验证在 Pydantic 和 DB CHECK 中重复 | 架构改进，非阻塞 |
| M4 | MEDIUM | Executor 和 Worker 有重复代码 | 可提取公共函数，非阻塞 |
| M6 | MEDIUM | pipeline_stage 无 DB 索引 | 低频查询场景，性能优化留后 |
| M7 | MEDIUM | db_path 无路径验证 | 配置值非用户输入 |
| M9 | MEDIUM | Provider 每次请求创建新 httpx.AsyncClient | 性能优化留后 |
| L1 | LOW | lease recovery interval 硬编码 | 可后续加到 config |
| L2 | LOW | 默认绑定 0.0.0.0 | 内网服务可接受 |
| L3 | LOW | 无 API 认证 | 已在交付范围声明中标注 |

## 统一接入范式

> **修订说明（2026-04-22 17:30）**：以下接入范式已更新为最终冻结的 contract。
> 调用方上下文统一通过 `metadata={"caller_context": {...}}` 传递，不再使用独立的 `ref_type/ref_id/build_id/release_id/request_id` 参数。
> 完整 API 参考见 `docs/integration/llm-service-integration-guide.md`。

`LLMClient` 已更新，内含完整的 Mining 和 Serving 接入范式：

### Mining（批量异步）
```python
client = LLMClient()
# 批量提交 → Worker 后台执行 → 轮询结果
task_id = await client.submit(
    caller_domain="mining",
    pipeline_stage="retrieval_units",
    template_key="mining-question-gen",
    input={"section_title": title, "content": text},
    metadata={
        "caller_context": {
            "ref": {"type": "section", "id": section_id},
            "build_id": build_id,
        }
    },
)
result = await client.get_result(task_id)
```

### Serving（同步在线增强）
```python
client = LLMClient()
result = await client.execute(
    caller_domain="serving",
    pipeline_stage="normalizer",
    template_key="serving-query-rewrite",
    input={"query": user_query},
    metadata={"caller_context": {"request_id": request_id}},
)
```

## 验证结果

- 79 个测试全部通过
- 覆盖：task 提交、attempt 重试、结果解析、schema 校验、失败记录、调用方上下文透传、模板展开、模板输出类型合同、request_id 贯通、lease recovery、API CRUD

## 审查重点

建议 Codex 重点审查：

1. **并发安全**：`main.py` 中三连接模型（API DB / Worker DB / Recovery DB）是否真正隔离
2. **模板合同**：`service.py:82-84` caller → template → "json_object" fallback 链是否与 Codex 预期一致
3. **null guard 完整性**：`executor.py` 和 `task_manager.py` 中新增的 `if row is None: return` 是否覆盖所有路径
4. **pipeline_stage pattern**：`models.py:14` 的 pattern 是否与 Mining/Serving 实际 stage 命名兼容
5. **统一接入范式**：`client.py` 中 Mining/Serving 示例是否满足两者的实际调用需求
