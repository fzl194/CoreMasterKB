# Handoff: v1.1 Agent Serving Rewrite

> 状态：已审查

**Date:** 2026-04-21
**From:** Claude Serving
**To:** Codex
**Task:** TASK-20260421-v11-agent-serving

---

## 任务目标

完全重写 Agent Serving 模块，从 M1 的 canonical/ EvidencePack 模型升级到 v1.1 的三层架构读取链路。

## 实现范围

### 核心模块重写

| 模块 | 文件 | 状态 |
|------|------|------|
| 数据模型 | `schemas/models.py` | 重写 → ContextPack, ActiveScope, ContextRelation |
| 常量 | `schemas/constants.py` | 重写 → v1.1 intent/role/kind/issue 常量 |
| 检索接口 | `retrieval/retriever.py` | 新建 → Retriever 抽象类 |
| FTS5 检索 | `retrieval/bm25_retriever.py` | 新建 → FTS5BM25Retriever + jieba 分词 |
| 图扩展 | `retrieval/graph_expander.py` | 新建 → GraphExpander BFS + parse_source_refs |
| LLM 客户端 | `application/planner.py` | 新建 → LLMRuntimeClient (placeholder) |
| Normalizer | `application/normalizer.py` | 重写 → LLM first + rule fallback, dict scope |
| Normalizer 配置 | `application/normalizer_config.py` | 重写 → 简化配置 |
| Assembler | `application/assembler.py` | 重写 → ContextAssembler: seed→source→expand→pack |
| Repository | `repositories/asset_repo.py` | 重写 → resolve_active_scope, resolve_source_segments |
| API | `api/search.py` | 重写 → 单 /search 端点, ContextPack 输出 |
| main.py | `main.py` | 未改动（保持 DB 注入） |
| schema_adapter | `repositories/schema_adapter.py` | 未改动（读取 v1.1 DDL） |

### 测试

| 测试文件 | 用例数 | 说明 |
|---------|--------|------|
| test_models.py | 11 | ContextPack, ActiveScope, QueryPlan 序列化 |
| test_normalizer.py | 20 | 命令/意图/scope/关键词提取 |
| test_asset_repo.py | 12 | ActiveScope, source drill-down, relations, documents |
| test_assembler.py | 6 | seed items, source drill-down, graph expansion |
| test_api_integration.py | 11 | 端到端: health, search, ContextPack 结构, 503 |
| test_schema_adapter.py | 4 | v1.1 DDL 表和字段验证 |
| test_mining_contract.py | 0 (1 skipped) | 等待 Mining v1.1 产出 |

**总计: 66 passed, 1 skipped, 0 failed**

## 关键设计决策

1. **ContextPack 替代 EvidencePack**: 独立的 `relations: list[ContextRelation]` 作为一等结构
2. **ActiveScope**: 包含 `document_snapshot_map` (document_id→snapshot_id)，不仅是 snapshot_ids
3. **source_refs_json 解析**: 通过 `parse_source_refs()` 提取 raw_segment_ids 进入正式读取逻辑
4. **Retriever 接口**: 抽象 Retriever 协议，FTS5BM25Retriever 为首实现，预留 VectorRetriever slot
5. **GraphExpander**: SQL BFS over asset_raw_segment_relations，seed 来自 source_refs_json
6. **Normalizer**: LLM Runtime client 优先 + 规则 fallback，scope 使用通用 dict 而非固定 QueryScope
7. **CJK 分词**: 应用层 jieba 分词 + FTS5 unicode61，`\b` word boundary 不用于 CJK 上下文
8. **唯一 /search 端点**: 移除 /command-usage，command 类问题由 intent 层覆盖
9. **Release 验证**: 0/1/>1 active release 分别返回 503/正常/500

## 不在本次范围

- LLM Runtime 实际连接（placeholder）
- Vector retriever 实现
- Reranker 实现
- Mining v1.1 契约测试（等 Mining 产出新 schema DB）
- 性能优化和缓存

## 已知风险

1. **FTS5 中文匹配**: jieba 分词后 tokens 与 unicode61 tokenizer 可能不完全对齐，部分中文查询召回率可能偏低
2. **LLM Normalizer**: 当前 placeholder，实际 LLM 连接需要 agent_llm_runtime 服务
3. **契约测试**: 无法验证与 Mining v1.1 真实输出的兼容性，需 Mining 产出新 DB 后补充

## Codex 审查建议

1. 检查 `resolve_active_scope` 的 SQL JOIN 路径是否与 build_document_snapshots schema 一致
2. 检查 GraphExpander 的 BFS 边界条件（空 frontier、环检测）
3. 检查 `_escape_fts_query` 的安全性（FTS5 注入风险）
4. 检查 assembler 中 source_refs_json 解析后 segments 无结果时的容错
