# M1 Agent Serving — Claude Serving 交接文档

> 日期: 2026-04-17
> 任务: TASK-20260415-m1-agent-serving
> 状态: **M1 实现完成**，39/39 测试通过

## 任务目标

实现 Agent 服务使用态在线查询最小闭环：

```text
Agent/Skill 请求 → 查询约束识别 → 检索 L1 canonical_segments → 通过 L2 下钻 L0 raw_segments → 返回 context pack
```

## 本次实现范围

| 组件 | 文件 | 状态 |
|------|------|------|
| Schema Adapter | `serving/repositories/schema_adapter.py` | ✅ |
| Pydantic Models | `serving/schemas/models.py` | ✅ |
| Asset Repository | `serving/repositories/asset_repo.py` | ✅ |
| Query Normalizer | `serving/application/normalizer.py` | ✅ |
| Context Assembler | `serving/application/assembler.py` | ✅ |
| Search API | `serving/api/search.py` | ✅ |
| Health API | `serving/api/health.py` | ✅ |
| Main App | `serving/main.py` | ✅ |
| Test Fixtures | `tests/conftest.py` | ✅ |
| Unit Tests | `tests/test_*.py` (6 files) | ✅ |
| Integration Tests | `tests/test_api_integration.py` (7 tests) | ✅ |

## 明确不在本次范围内的内容

- **SearchPlanner**（检索策略规划）→ M2
- **context_assemble 独立端点** → M2
- **LogRepository**（retrieval_logs 写入）→ M2
- **init_serving.sql**（独立 serving schema）→ M2
- Vector 检索 / embedding → M3
- Markdown 解析 / 文档导入 / 去重归并 → Mining 任务

## 改动文件清单

### 新增
- `agent_serving/serving/repositories/schema_adapter.py`
- `agent_serving/serving/repositories/asset_repo.py`
- `agent_serving/serving/application/normalizer.py`
- `agent_serving/serving/application/assembler.py`
- `agent_serving/serving/api/search.py`
- `agent_serving/serving/schemas/models.py`
- `agent_serving/tests/conftest.py`
- `agent_serving/tests/test_schema_adapter.py`
- `agent_serving/tests/test_models.py`
- `agent_serving/tests/test_asset_repo.py`
- `agent_serving/tests/test_normalizer.py`
- `agent_serving/tests/test_assembler.py`
- `agent_serving/tests/test_api_integration.py`

### 修改
- `agent_serving/serving/main.py`（lifespan + DB 注入）
- `agent_serving/serving/api/health.py`（保持不变）
- `pyproject.toml`（添加 aiosqlite 依赖）

### 不修改
- `knowledge_assets/schemas/001_asset_core.sql`（共享只读）
- `knowledge_mining/**`（禁止修改）

## 关键设计决策

1. **Schema Adapter**：从 `001_asset_core.sql` 自动生成 SQLite DDL，不维护私有 DDL
2. **conflict_candidate 处理**：L2 中 `relation_type=conflict_candidate` 的记录转为 Uncertainty，不出现在 raw_segments 中
3. **参数化 seed data**：conftest 使用 `executemany` + 参数化查询（`executescript` 无法正确处理 JSON 数组中的逗号）
4. **DB 注入**：通过 `app.state.db` + FastAPI lifespan，API 层通过 `Request.app.state.db` 获取
5. **纯 SQL 检索**：M1 使用 LIKE/command_name 精确匹配，不引入 vector 依赖

## 已执行验证

```
39/39 tests passed:
- 3 schema adapter tests
- 4 model tests
- 10 asset repo tests
- 9 normalizer tests
- 4 assembler tests
- 7 API integration tests (health, search, command-usage, conflict)
- 2 smoke tests (health, import)
```

## 未验证项

- 生产 PostgreSQL 连接（当前仅 SQLite dev mode）
- 高并发场景下的连接池
- 实际 Mining 产出数据的端到端验证

## 已知风险

1. **Normalizer 规则硬编码**：M1 使用固定映射表，无法覆盖所有中文操作词变体
2. **LIKE 性能**：`search_text LIKE '%keyword%'` 无法利用索引，大数据量下可能慢
3. **keyword 提取**：中文分词依赖空格/标点分割，对无空格的中文短句效果差

## 指定给 Codex 的审查重点

1. **Schema Adapter 正确性**：确认 PG→SQLite 转换覆盖了所有必要类型（UUID→TEXT, JSONB→TEXT, TIMESTAMPTZ→TEXT, NUMERIC→REAL）
2. **conflict_candidate 行为**：确认冲突不出现在 raw_segments，只出现在 uncertainties
3. **设计文档同步**：确认 Planner/context_assemble 已标注 M2+，文件清单与实际代码一致
4. **seed data 与 schema v0.4 兼容性**：确认 conftest 的 INSERT 列与 `001_asset_core.sql` v0.4 一致

## 提交记录

```
88125cf [claude-serving]: add aiosqlite dependency for dev mode SQLite
778cd83 [claude-serving]: add Pydantic request/response models
4ff8f6a [claude-serving]: add schema adapter to generate SQLite DDL from shared asset schema
657375f [claude-serving]: add test fixtures with schema from shared contract and conflict_candidate seed
204c78d [claude-serving]: post plan revision notice and update message index
162ad78 [claude-serving]: revise impl plan v1.1 — fix Codex review P1-P2
aaa6edc [claude-serving]: publish M1 Agent Serving implementation plan
9073161 [claude-serving]: publish M1 agent serving design document
5269e6d [claude-serving]: submit M1 design and update task tracking
cb2541c [claude-serving]: add core query pipeline (AssetRepository, Normalizer, Assembler)
ed293bd [claude-serving]: add search API endpoints with DB injection and integration tests
```
