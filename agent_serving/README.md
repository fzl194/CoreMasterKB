# Agent Serving — 方案架构文档

> 在线知识检索层：Active Release → 混合检索 → ContextPack
> 版本：v1.1（生产就绪）| 数据库：asset_core（只读）| 端口：8000

`agent_serving` 是 CoreMasterKB 的在线知识使用层。它面向 Skill / Agent 提供 HTTP API，从 Mining 生成的知识资产数据库中读取唯一 active release，检索 `retrieval_units`，通过 `source_refs_json` 下钻到 `raw_segments` 和 `relations`，最后返回结构化的 `ContextPack`。

它不负责解析文档、不做批量去重、不写入知识资产表，也不生成最终自然语言答案。它的输出是给上层 Agent 使用的上下文包。

## 读取链路

```text
active release (asset_publish_releases)
  → build (asset_builds)
  → build_document_snapshots (asset_build_document_snapshots)
  → retrieval_units (asset_retrieval_units)  ← 主检索对象
  → source_refs_json → raw_segments (asset_raw_segments)
  → relations (asset_raw_segment_relations)  ← 上下文扩展
  → documents (asset_documents)  ← 来源引用
```

核心边界：

- Serving 只读 `asset_*` 知识资产表。
- Serving 不 import `knowledge_mining`。
- Mining 和 Serving 只通过 `databases/asset_core/schemas/001_asset_core.sqlite.sql` 对接。
- 查询主入口是 `/api/v1/search`（唯一端点）。
- v1.1 使用 FTS5 BM25 检索 + jieba 分词 + LIKE fallback。
- LLM 调用统一走 `agent_llm_runtime`，Serving 内部不建模型调用体系。

## 整体架构

```text
Agent / Skill
  → FastAPI /api/v1/search
  → Normalizer (LLM first + rule fallback)
  → QueryPlan
  → AssetRepository.resolve_active_scope()
  → Retriever (FTS5BM25Retriever)
  → ContextAssembler
    → seed items from retrieval_units
    → source drill-down via parse_source_refs
    → graph expansion via GraphExpander BFS
  → ContextPack
```

代码分层：

| 层 | 目录 | 职责 |
|---|---|---|
| API 层 | `serving/api/` | HTTP 路由、请求校验、调用应用层 |
| Application 层 | `serving/application/` | Normalizer、ContextAssembler 组装、LLM Runtime client placeholder |
| Retrieval 层 | `serving/retrieval/` | Retriever 抽象、FTS5BM25Retriever、GraphExpander |
| Repository 层 | `serving/repositories/` | 只读 SQLite asset tables：ActiveScope、source drill-down、relations |
| Schema 层 | `serving/schemas/` | ContextPack、ActiveScope、ContextRelation 等 Pydantic 模型和常量 |
| 测试 | `tests/` | 单元、API 集成、schema 适配、Mining 契约测试 |

## 核心模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| 数据模型 | `schemas/models.py` | ContextPack, ActiveScope, ContextRelation, ContextItem, NormalizedQuery |
| 常量 | `schemas/constants.py` | v1.1 intent/role/kind/issue 常量 |
| 检索接口 | `retrieval/retriever.py` | Retriever 抽象类，预留 VectorRetriever slot |
| FTS5 检索 | `retrieval/bm25_retriever.py` | FTS5 BM25 + jieba 分词 + LIKE fallback |
| 图扩展 | `retrieval/graph_expander.py` | SQL BFS over raw_segment_relations + parse_source_refs |
| Normalizer | `application/normalizer.py` | LLM first + rule fallback，dict scope |
| Assembler | `application/assembler.py` | ContextPack 组装：seed → source → expand → pack |
| Repository | `repositories/asset_repo.py` | resolve_active_scope, resolve_source_segments, get_relations |
| API | `api/search.py` | 单 /search 端点，ContextPack 输出 |

## ContextPack 结构

v1.1 输出模型：

| 字段 | 含义 |
|---|---|
| `query` | 查询元信息（intent、entities、scope、keywords） |
| `items` | 检索结果项列表（retrieval_unit / raw_segment） |
| `relations` | 一等关系结构（from_id, to_id, relation_type） |
| `sources` | 文档来源（document_key, title, relative_path） |
| `issues` | 查询/数据问题提示 |
| `suggestions` | 建议的追问 |
| `debug` | 调试信息（plan、scope、candidate_count），可选 |

### ContextItem

| 字段 | 含义 |
|---|---|
| `id` | 检索单元或原始片段 ID |
| `kind` | `retrieval_unit` 或 `raw_segment` |
| `role` | `seed`（主召回）、`context`（来源下钻）、`support`（图扩展） |
| `text` | 文本内容 |
| `score` | 检索得分 |
| `metadata` | 附加元数据（document_key, section_path 等） |

### ContextRelation

| 字段 | 含义 |
|---|---|
| `id` | 关系 ID |
| `from_id` | 起始项 ID |
| `to_id` | 目标项 ID |
| `relation_type` | 关系类型（next, reference, parent 等） |

## 如何启动

### 1. 使用 Mining 生成的 SQLite DB

```powershell
$env:COREMASTERKB_ASSET_DB_PATH="D:\mywork\KnowledgeBase\CoreMasterKB\data\m1_contract_corpus\m1_contract_asset.sqlite"
python -m agent_serving.serving.main
```

或通过 uvicorn：

```powershell
uvicorn agent_serving.serving.main:app --host 127.0.0.1 --port 8000
```

### 2. Dev 空库模式

如果没有设置 `COREMASTERKB_ASSET_DB_PATH`，服务会创建 in-memory SQLite 并建表。`/health` 可用，但 `/search` 会因为没有 active release 返回 503。

## API

### `GET /health`

```powershell
curl http://127.0.0.1:8000/health
```

返回：

```json
{"status": "ok"}
```

### `POST /api/v1/search`

通用检索主入口（唯一端点）。

最小请求：

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/search `
  -H "Content-Type: application/json" `
  -d "{\"query\":\"ADD APN 怎么写\"}"
```

带 scope：

```json
{
  "query": "ADD APN 参数说明",
  "scope": {"products": ["UDG"]}
}
```

带 debug 模式：

```json
{
  "query": "5G eMBB",
  "debug": true
}
```

### Active Release 规则

| 情况 | 行为 |
|---|---|
| 0 个 active release | API 返回 503 |
| 1 个 active release | 正常查询 |
| 多个 active release | DB UNIQUE 约束阻止（代码防御性检查） |

## 测试

```powershell
python -m pytest agent_serving/tests -q
```

| 文件 | 用例数 | 覆盖点 |
|---|---|---|
| `test_models.py` | 11 | ContextPack, ActiveScope, QueryPlan 序列化 |
| `test_normalizer.py` | 20 | 命令/意图/scope/关键词提取 |
| `test_asset_repo.py` | 12 | ActiveScope, source drill-down, relations, documents |
| `test_assembler.py` | 6 | seed items, source drill-down, graph expansion |
| `test_api_integration.py` | 11 | 端到端: health, search, ContextPack 结构, 503 |
| `test_schema_adapter.py` | 4 | v1.1 DDL 表和字段验证 |
| `test_mining_contract.py` | 1 skipped | 等待 Mining v1.1 产出 |

**总计：66 passed, 1 skipped, 0 failed**

## 后续演进方向

### 预留扩展点

| 方向 | 预留位置 | 说明 |
|------|---------|------|
| Vector retrieval | `retrieval/retriever.py` → VectorRetriever | 抽象 Retriever 接口，FTS5 为首实现 |
| Reranker | `pipeline/reranker.py` | 已有 ScoreReranker（规则），预留 LLM/Cross-Encoder |
| LLM planner | `application/planner.py` → LLMPlannerProvider | 已实现 LLM + 规则双模式 |
| Query rewrite | Normalizer LLM first | LLM 返回时自动使用，rule fallback |
| Ontology expansion | QueryPlan.expansion 字段 | 预留，未实现 |
| 缓存 | Repository 层 | 未实现，按需加入 |

### v1.2 演进路线

#### 检索策略增强（核心差异化）

| 方向 | 说明 | 预期收益 |
|------|------|---------|
| **向量检索器** | BGE-M3 多语言 embedding + cosine 相似度匹配 | 弥合同义词/表述差异，补充 FTS5 关键词盲区 |
| **HyDE** | LLM 生成假设回答文档，取其 embedding 做匹配 | 弥合 query-doc 语义鸿沟 |
| **父子层级分块** | Mining 侧生成 parent-child 关系，Serving 按需返回 | 小 chunk 精准匹配 + 大 chunk 完整上下文 |
| **上下文增强检索** | Mining 侧 LLM 为每个 chunk 生成上下文描述 | 减少检索失败率 |

#### 排序质量提升

| 方向 | 说明 |
|------|------|
| **Cross-Encoder 精排** | 对 RRF 融合后的 top-K 候选做交叉编码器重排 |
| **LLM Reranker** | 使用 LLM 对候选进行相关性评分 |
| **语篇关系扩展** | 利用 Mining 侧的语篇关系（elaboration/cause_effect/contrast）做证据扩展 |

#### 架构增强

| 方向 | 说明 |
|------|------|
| **结果缓存** | Redis 或内存缓存热门查询结果 |
| **分页支持** | 大结果集分页返回 |
| **多 channel** | 支持 dev/staging/prod 多个 release channel |
| **WebSocket 实时推送** | 查询进度和部分结果实时推送 |

### v1.2+ 远期方向

- **声明式查询引擎**：seed / expand / combine / aggregate / project 五个代数原语
- **双层图遍历**：推理层（本体语义边）+ 溯源层（Fact→Document 证据链）分离查询
- **社区摘要检索**：GraphRAG 式社区检测后，按社区聚合摘要
- **五维置信度**：source_authority × extraction_method × ontology_fit × cross_source_consistency × temporal_validity

## 和 Mining 的边界

Mining 做：

- 扫描输入文件夹，解析文档
- 生成 raw_segments, retrieval_units, relations
- 维护 build / release 生命周期

Serving 做：

- 读取唯一 active release
- FTS5 检索 retrieval_units
- source_refs 下钻 raw_segments
- 图扩展 relations
- 返回 ContextPack

Serving 不做：

- 重新解析文档或切片
- 写入 asset tables
- 修改 release 状态
- 调用 LLM 生成答案

## 开发入口速查

| 想改什么 | 优先看哪里 |
|---|---|
| 新增 API | `serving/api/` |
| 修改查询理解规则 | `serving/application/normalizer.py` |
| 修改 ContextPack 或响应结构 | `serving/schemas/models.py` |
| 修改检索召回 | `serving/retrieval/bm25_retriever.py` |
| 修改图扩展逻辑 | `serving/retrieval/graph_expander.py` |
| 修改 ActiveScope / source 下钻 | `serving/repositories/asset_repo.py` |
| 修改 ContextPack 组装 | `serving/application/assembler.py` |
| 修改 DB 初始化 | `serving/main.py`, `serving/repositories/schema_adapter.py` |
| 增加真实 Mining DB 契约测试 | `tests/test_mining_contract.py` |

## 相关文档

- [Asset Core Schema](../databases/asset_core/schemas/001_asset_core.sqlite.sql) — Serving 读取的数据表结构
- [v1.1 架构文档](../docs/architecture/2026-04-21-coremasterkb-v1.1-architecture.md)
- [v1.2 演进 Backlog](../.dev/2026-04-22-v12-evolution-backlog.md)
- [LLM 集成指南](../docs/integration/llm-service-integration-guide.md)
- [架构演示](../docs/architecture/coremasterkb-v1.2-architecture.html)
