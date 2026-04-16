# M1 Agent Serving 设计文档

> 版本: v1.1（实现后同步）
> 日期: 2026-04-15 / 更新: 2026-04-17
> 作者: Claude Serving
> 任务: TASK-20260415-m1-agent-serving
> 状态: 已实现，39/39 测试通过

## 1. 任务目标

实现在线使用态最小闭环：

```text
Agent/Skill 请求 -> 查询约束识别 -> 检索 L1 canonical_segments -> 通过 L2 选择 L0 raw_segments -> 返回 context pack。
```

## 2. 设计决策

### 2.1 检索方式：纯 SQL 全文检索

- L1 用 `search_text` 字段 + PostgreSQL `to_tsvector` / SQLite LIKE
- L2 下钻用 SQL JOIN + 条件过滤
- M1 不做 vector 检索（无 embedding 数据），后续 M3 扩展
- Schema 已有 FTS 索引，直接可用

理由：零额外依赖，M1 阶段 keyword/command 精确匹配已覆盖核心场景。

### 2.2 测试数据策略

- 测试用 SQLite in-memory + 按 asset schema 建表
- 手写 seed 数据模拟 L0/L1/L2 示例记录
- 不等待 Mining 实现完成

### 2.3 Schema 使用方式

- 只读取 `knowledge_assets/schemas/001_asset_core.sql` 定义的 asset 表
- Serving 自建 `init_serving.sql`（retrieval_logs）
- 不修改 asset schema

## 3. 总体架构

```text
Skill 请求
  ↓
FastAPI API 层 (api/)
  ↓
Application 层 (application/)
  ├── QueryNormalizer   — 解析查询约束
  └── ContextAssembler  — 组装 context pack
  ↓
Repository 层 (repositories/)
  ├── AssetRepository   — 只读 L1/L2/L0
  └── LogRepository     — 写入 retrieval_logs
  ↓
SQLite (dev) / PostgreSQL (prod)
```

## 4. 模块与文件清单

| 文件 | 职责 |
|------|------|
| `agent_serving/serving/repositories/asset_repo.py` | 只读 asset 表 |
| `agent_serving/serving/repositories/schema_adapter.py` | PG DDL → SQLite DDL 转换 |
| `agent_serving/serving/application/normalizer.py` | 查询约束识别 |
| `agent_serving/serving/application/assembler.py` | context pack 组装 |
| `agent_serving/serving/schemas/models.py` | Pydantic request/response |
| `agent_serving/serving/api/search.py` | `POST /api/v1/search` + `POST /api/v1/command-usage` |
| `agent_serving/serving/api/health.py` | `GET /health` |
| `agent_serving/serving/main.py` | FastAPI app，lifespan DB 初始化 |
| `agent_serving/tests/conftest.py` | 测试 fixture（参数化 seed data） |
| `agent_serving/tests/test_normalizer.py` | Normalizer 测试 |
| `agent_serving/tests/test_asset_repo.py` | Repository 测试 |
| `agent_serving/tests/test_assembler.py` | Assembler 测试（conflict 处理） |
| `agent_serving/tests/test_schema_adapter.py` | Schema 转换测试 |
| `agent_serving/tests/test_models.py` | 模型序列化测试 |
| `agent_serving/tests/test_api_integration.py` | API 集成测试 |

> **M2+ 计划**：`planner.py`（检索策略规划）和 `context_assemble.py`（独立上下文组装端点）推迟到 M2。M1 中 Normalizer 直接驱动 search + drill_down，Assembler 直接组装 pack。

## 5. 数据流

### 5.1 命令查询流

```text
请求 {query: "UDG V100R023C10 ADD APN 怎么写"}
  → Normalizer: {command: "ADD APN", product: "UDG", product_version: "V100R023C10"}
  → AssetRepo.search_canonical(command_name="ADD APN")
  → L1 命中，has_variants=true
  → AssetRepo.drill_down(canonical_id, product="UDG", version="V100R023C10")
  → 通过 L2 选择对应 L0
  → 组装 context pack 返回
```

### 5.2 通用搜索流

```text
请求 {query: "5G 是什么"}
  → Normalizer: {intent: "general"}
  → AssetRepo.search_canonical(keyword="5G")
  → L1 命中，has_variants=false
  → 直接用 canonical_text
  → 组装 context pack 返回
```

### 5.3 约束不足流

```text
请求 {query: "ADD APN 怎么写"}
  → Normalizer: {command: "ADD APN", missing: ["product", "version"]}
  → L1 命中，has_variants=true
  → 约束不足
  → 返回 canonical_text + uncertainties + suggested_followups
```

### 5.4 冲突候选流

```text
请求命中 conflict_candidate 类型的 L2
  → 不强行回答
  → 返回冲突来源，提示需要确认产品/版本
```

## 6. Query Normalizer 规则

M1 使用硬编码规则：

- 操作词映射：`新增→ADD, 修改→MOD, 删除→DEL, 查询→SHOW/LST/DSP, 设置→SET`
- 命令模式：`ADD|MOD|DEL|SET|SHOW|LST|DSP\s+[A-Z]+`
- 产品识别：`UDG|UNC|UPF|AMF|SMF|PCF|UDM`
- 版本识别：`V\d+R\d+C\d+`
- 网元识别：`AMF|SMF|UPF|UDM|PCF|NRF|AUSF|BSF`

## 7. Context Pack 结构

```text
{
  query: str,
  intent: str,                     // "command_usage" | "general_query"
  normalized_query: str,
  key_objects: {
    command, product, product_version, network_element
  },
  answer_materials: {
    canonical_segments: [{id, segment_type, title, canonical_text, command_name, has_variants, variant_policy}],
    raw_segments: [{id, segment_type, raw_text, command_name, section_path, section_title}]
  },
  sources: [{document_key, section_path, segment_type, product, product_version, network_element}],
  uncertainties: [{field, reason, suggested_options}],
  suggested_followups: [str],
  debug_trace: {...}               // 仅 debug 模式
}
```

## 8. SQLite Dev 适配

- `init_db.py` 支持 SQLite 模式（去掉 PostgreSQL 特有语法如 `CREATE EXTENSION`、`SCHEMA`）
- Repository 通过 `aiosqlite` 异步访问
- 测试用内存 SQLite

## 9. 依赖新增

```toml
"aiosqlite>=0.20"    # dev mode SQLite 异步访问
```

## 10. 不做的内容

- vector 检索
- Markdown 解析/导入
- embedding 批处理
- 写 asset 表
- import knowledge_mining
- 修改 knowledge_assets/dictionaries
- 发布版本生成

## 11. 与 Mining 任务的接口边界

| 接口 | 方向 | 说明 |
|------|------|------|
| `knowledge_assets/schemas/001_asset_core.sql` | 共享只读 | 两边都读，不修改 |
| `knowledge_assets/schemas/init_serving.sql` | Serving 专有 | Mining 不读不写 |
| 数据库 asset.* 表 | Mining 写，Serving 读 | 通过数据库对接 |
| 数据库 serving.* 表 | Serving 读写 | Mining 不涉及 |

如需变更共享 schema，必须先在 `docs/messages/TASK-20260415-m1-agent-serving.md` 中说明兼容性影响。
