# Knowledge Mining — 方案架构文档

> 离线知识挖掘模块：原始文档 → 结构化知识资产
> 版本：v1.1（生产就绪）| 数据库：asset_core + mining_runtime | Pipeline：9 阶段

## 1. 系统定位

`knowledge_mining` 将一个普通文件夹中的原始资料（Markdown、纯文本等）经过扫描、解析、切片、增强、关系构建和检索单元生成，最终通过 shared snapshot → build → release 发布到 `asset_core`，供 `agent_serving` 只读检索。

**核心价值：**把非结构化的技术文档变成可被 Agent 直接消费的结构化知识资产。

## 2. 两阶段 Pipeline

### Phase 1: Document Mining（文档级，每文档独立，可并行）

```
ingest → parse → segment → enrich → build_relations → build_retrieval_units → select_snapshot
```

### Phase 2: Build & Publish（全局操作，所有文档处理完成后串行执行）

```
assemble_build → validate_build → publish_release
```

```
input folder
  → ingestion (递归扫描 → RawFileData)
  → parsers (MarkdownParser / PlainTextParser / PassthroughParser)
  → structure (markdown-it → SectionNode 树)
  → segmentation (SectionNode → RawSegmentData，heading 独立成段)
  → enrich (规则增强：entity_refs、heading_role、table metadata)
  → relations (结构关系：previous/next、same_section、section_header_of)
  → retrieval_units (raw_text + contextual_text + entity_card)
  → snapshot (共享快照：document + snapshot + link 三层)
  → publishing (build 合并 + release 激活)
  → asset_core.sqlite + mining_runtime.sqlite
```

## 3. 模块架构

```
knowledge_mining/mining/
├── models.py            # 12 个 frozen dataclass + 11 个 frozenset 常量，对齐 SQL schema
├── db.py                # AssetCoreDB + MiningRuntimeDB 双库适配器，DDL 从共享 SQL 加载
├── hash_utils.py        # 保守 snapshot 归一化 + SHA256
├── text_utils.py        # CJK-aware tokenization、归一化、相似度计算
│
├── ingestion/           # 递归文件夹扫描 → RawFileData（支持 .md/.txt/.html/.pdf/.docx）
├── parsers/             # 解析器工厂：MarkdownParser / PlainTextParser / PassthroughParser
├── structure/           # markdown-it → SectionNode 树（保留 table/list/code 结构）
├── segmentation/        # SectionNode → RawSegmentData（heading 独立成段）
├── extractors.py        # RuleBasedEntityExtractor + DefaultRoleClassifier 接口定义
├── enrich/              # 规则增强：entity context、heading role、table metadata
├── relations/           # 结构关系构建：previous/next、same_section、section_header_of
├── retrieval_units/     # 检索单元生成：raw_text + contextual_text + entity_card + question_gen
├── snapshot/            # 共享快照：document/snapshot/link 三层选择与创建
├── publishing/          # build 组装（增量合并）+ release 激活
├── runtime/             # RuntimeTracker：阶段事件跟踪 + 断点续跑计划
├── jobs/run.py          # Pipeline 编排器（run + publish 两个入口）
├── llm_client.py        # LLM 服务 HTTP 客户端
└── llm_templates.py     # LLM 模板定义
```

## 4. 九阶段详解

### Stage 1: Ingest（摄取）

| 项目 | 说明 |
|------|------|
| 输入 | 文件夹路径 |
| 输出 | `list[RawFileData]` + 摄取摘要 |
| 逻辑 | 递归扫描 `.md/.txt/.html/.pdf/.doc/.docx`；计算 `raw_content_hash` 和 `normalized_content_hash`；跳过 manifest 等特殊文件 |
| 跳过条件 | 文件未变化（hash 相同） |

### Stage 2: Parse（解析）

| 项目 | 说明 |
|------|------|
| 输入 | `RawFileData.content` |
| 输出 | `SectionNode` 树结构 |
| 逻辑 | MarkdownParser：markdown-it-py 解析，保留 table/list/code；PlainTextParser：段落分块；PassthroughParser：不解析，仅登记 |
| 保留信息 | heading 层级、table 列结构、list 编号、code 语言标记 |

### Stage 3: Segment（分块）

| 项目 | 说明 |
|------|------|
| 输入 | `SectionNode` 树 + `DocumentProfile` |
| 输出 | `list[RawSegmentData]` |
| 逻辑 | Heading 独立成段（section_header_of 关系需要）；按 `block_type`（9 种）和 `semantic_role`（11 种）分类；生成 `content_hash` 和 `normalized_hash` |
| 关键设计 | 每个 segment 保留 `section_path`（JSON 路径数组）支持溯源到文档层级 |

### Stage 4: Enrich（增强）

| 项目 | 说明 |
|------|------|
| 输入 | `list[RawSegmentData]` |
| 输出 | 增强后的 `list[RawSegmentData]`（原地更新 entity_refs、metadata） |
| 逻辑 | RuleBasedEntityExtractor：正则提取命令/网络元素/参数实体；DefaultRoleClassifier：语义角色分类（parameter/example/constraint 等）；table metadata：列数、是否有参数列 |
| v1.2 增强 | LLM 替换规则引擎：summary、generated_question、语义关系 |

### Stage 5: Build Relations（构建关系）

| 项目 | 说明 |
|------|------|
| 输入 | `list[RawSegmentData]` |
| 输出 | `list[SegmentRelationData]` + segment_id 映射 |
| 逻辑 | 结构关系：previous/next（相邻）、same_section（同级，distance≤5 限制）、section_header_of（标题→内容）、same_parent_section |
| 关键设计 | 关系带 `weight / confidence / distance` 三维评估 |
| v1.2 增强 | 语篇关系：elaboration / cause_effect / contrast / condition — 24 种关系标签空间 |

### Stage 6: Build Retrieval Units（检索单元）

| 项目 | 说明 |
|------|------|
| 输入 | segments + seg_ids 映射 + 可选 LLM 问答生成器 |
| 输出 | `list[RetrievalUnitData]` |
| 逻辑 | `raw_text`：1:1 映射原始 segment；`contextual_text`：添加 section 路径前缀；`entity_card`：实体卡片，聚合同一实体引用；`generated_question`：LLM 生成问题（v1.2） |
| 同时产出 | `search_text`（FTS5 索引）、`facets_json`（过滤维度）、`source_refs_json`（溯源链） |

### Stage 7: Select Snapshot（共享快照）

| 项目 | 说明 |
|------|------|
| 输入 | 文档内容、配置、batch_id |
| 输出 | `(document_id, snapshot_id, link_id)` |
| 逻辑 | 三层模型：document（身份）→ snapshot（内容）→ link（映射）；归一化：CRLF→LF + 去尾空白 + 去空行 → SHA256；相同内容共享 snapshot |
| 关键约束 | 相同 `normalized_content_hash` 只存一份 snapshot |

### Stage 8: Assemble Build（组装构建）

| 项目 | 说明 |
|------|------|
| 输入 | snapshot 决策列表 |
| 输出 | `build_id` |
| 逻辑 | 自动判断 `full` / `incremental` 模式；文档分类：NEW / UPDATE / SKIP / REMOVE；与前一 build 合并（保留未变更文档） |
| 写入 | `asset_builds` + `asset_build_document_snapshots` |

### Stage 9: Publish Release（发布版本）

| 项目 | 说明 |
|------|------|
| 输入 | `build_id` |
| 输出 | `release_id` |
| 逻辑 | 激活新 release → 旧 active release 退役；同一 channel 只有一个 active release |
| 写入 | `asset_publish_releases` |

## 5. 数据库边界

| 数据库 | 职责 | Mining 写入 |
|--------|------|-------------|
| `asset_core.sqlite`（11 表） | 内容资产：documents, snapshots, segments, relations, retrieval_units, embeddings, builds, releases | 是（Phase 1 写 segments/relations/units，Phase 2 写 builds/releases） |
| `mining_runtime.sqlite`（3 表） | 过程状态：runs, run_documents, stage_events | 是 |
| `agent_llm_runtime.sqlite`（6 表） | LLM 调用审计 | 否（LLM Service 独立管理） |

## 6. Shared Snapshot 模型

v1.1 的核心内容复用机制：

```
asset_documents          — 逻辑文档身份（document_key 唯一）
asset_document_snapshots — 共享内容快照（normalized_content_hash 唯一）
asset_document_snapshot_links — 文档到快照的映射
```

**归一化策略（保守）：**
1. CRLF → LF
2. 每行去除尾部空白
3. 去除空行
4. SHA256

**关键特性：**
- 不同文档如果内容归一化后相同，共享同一个 snapshot
- UPDATE 时清理旧 snapshot 的 segments/relations/units
- SKIP 时直接重用现有 snapshot，不做任何处理

## 7. LLM 集成点

### 当前已实现（v1.2 新增）

| 阶段 | LLM 用途 | 模式 | 模板 |
|------|---------|------|------|
| retrieval_units | 问题生成（generated_question） | Batch async（submit_all → poll_all） | `mining-question-gen` |

### 规划中（v1.2 后续）

| 阶段 | LLM 用途 | 说明 |
|------|---------|------|
| enrich | 语义实体提取 | 替换 RuleBasedEntityExtractor |
| enrich | 摘要/分类 | section summary、document_type 分类 |
| relations | 语篇关系提取 | 24 种关系标签空间（elaboration / cause_effect / contrast） |
| retrieval_units | 上下文增强 | Contextual Retrieval — 为每个 chunk 生成上下文描述 |
| retrieval_units | 假设文档嵌入 | HyDE — LLM 生成假设回答用于 embedding 匹配 |

**集成架构：**通过 `llm_client.py` + `llm_templates.py` 调用 LLM Service，LLM 不可用时降级到 NoOp（不阻塞 Pipeline）。

## 8. 关键设计决策

### 8.1 不可变数据模式

所有内部 dataclass 使用 `frozen=True`，防止副作用，便于调试和并发安全。

### 8.2 结构化信息保留

SectionNode 树保留 table 的列结构、list 的编号、code 的语言标记，确保下游检索单元可以基于结构生成高质量内容。

### 8.3 FTS5 全文索引

通过 SQLite FTS5 虚拟表 + 触发器实现自动同步。中文支持 jieba 分词（v1.2）。

### 8.4 断点续跑

RuntimeTracker 记录每个阶段的 stage_event，支持从失败点恢复执行（ResumePlan）。

## 9. 如何运行

```python
from knowledge_mining.mining.jobs.run import run, publish
from knowledge_mining.mining.models import BatchParams

# 完整 pipeline（Phase 1 + Phase 2）
result = run(
    "/path/to/input/folder",
    asset_core_db_path="asset_core.sqlite",
    mining_runtime_db_path="mining_runtime.sqlite",
    batch_params=BatchParams(
        default_source_type="folder_scan",
        default_document_type="command",
        batch_scope={"products": ["CloudCore"]},
        tags=["coldstart"],
    ),
)

# 仅 Phase 1（不构建 build/release）
result = run("/path/to/input", phase1_only=True)

# 对已完成的 run 发布 release
publish(result["run_id"])
```

## 10. 测试

```bash
python -m pytest knowledge_mining/tests/test_v11_pipeline.py -v
# 30 个测试覆盖：models、DB adapters、hash utils、ingestion、structure、
# segmentation、extractors、enrich、relations、retrieval_units、snapshot、
# publishing、端到端 pipeline
```

## 11. 当前状态（v1.1）

### 已完成

- 完整的两阶段 Pipeline（9 阶段端到端）
- 多格式解析器（Markdown / PlainText / Passthrough）
- 结构化分块（9 种 block_type + 11 种 semantic_role）
- 规则增强（实体提取 + 角色分类 + 表格元数据）
- 结构关系构建（4 种关系类型 + distance/weight/confidence）
- 多载体检索单元（raw_text / contextual_text / entity_card）
- Shared Snapshot 共享去重
- 增量构建（full + incremental 双模式）
- 版本发布（staging → active → retired 状态流转）
- LLM 问题生成（batch async 模式）
- jieba 中文分词搜索
- 断点续跑支持
- 30 个测试覆盖

### 已知限制

- HTML/PDF/DOC/DOCX 只登记不解析正文
- Enrich 阶段是规则驱动，非 LLM
- Relations 只有结构关系，缺少语篇语义关系
- document_key 生成策略在多产品场景下可能冲突
- 删除文件检测（REMOVE 语义）未实现
- same_section 关系在大文档下 O(n²) 爆炸
- mining_runs 计数不够准确

## 12. v1.2 演进方向

### 架构级（HIGH 优先级）

| EVO | 方向 | 说明 |
|-----|------|------|
| EVO-01 | document_key namespace | 防止多产品场景下 document_key 冲突 |
| EVO-02 | REMOVE 语义 | 检测被删除的文件，在 build 中标记 remove |
| EVO-05 | same_section 距离限制 | 控制 O(n²) 关系爆炸 |
| EVO-06 | Build validate 空操作修复 | 空 build 不应通过验证 |

### Pipeline 改进（HIGH/MEDIUM）

| EVO | 方向 | 说明 |
|-----|------|------|
| EVO-03 | scope 一等实体 | 将 scope 从 JSON 字段提升为独立维度 |
| EVO-04 | document_type 自动分类 | LLM 自动判断文档类型 |
| EVO-07 | Snapshot 复用一致性 | UPDATE 时清理旧数据的完整性保证 |
| EVO-08 | Enrich batch 语义 | 利用 LLM context window 批量处理 |

### 语义增强（核心差异化）

| 方向 | 说明 |
|------|------|
| 语篇关系 | 24 种 RST 关系标签空间，LLM 零样本提取 |
| 父子层级分块 | 小 chunk 精准匹配 + 大 chunk 完整上下文 |
| 上下文增强检索 | LLM 为每个 chunk 生成上下文描述 |
| HyDE | LLM 生成假设文档用于 embedding 匹配 |
| 社区摘要 | GraphRAG 式社区检测 + 聚合摘要 |
| 跨文档实体合并 | 实体链接 + 知识图谱构建 |

## 13. 新增阶段/模块指南

1. 在 `models.py` 中定义 frozen dataclass
2. 在对应目录下创建模块（如 `relations/semantic/`）
3. 在 `jobs/run.py` 的 pipeline 编排中插入新阶段
4. 在 `mining_runtime` 的 stage 枚举中添加新阶段名
5. 添加对应测试
6. 更新 `db.py` 中的 stage_events 记录

## 14. 相关文档

- [Asset Core Schema](../databases/asset_core/schemas/001_asset_core.sqlite.sql)
- [Mining Runtime Schema](../databases/mining_runtime/schemas/001_mining_runtime.sqlite.sql)
- [LLM 集成指南](../docs/integration/llm-service-integration-guide.md)
- [v1.1 架构文档](../docs/architecture/2026-04-21-coremasterkb-v1.1-architecture.md)
- [v1.2 演进 Backlog](../.dev/2026-04-22-v12-evolution-backlog.md)
- [架构演示](../docs/architecture/coremasterkb-v1.2-architecture.html)
