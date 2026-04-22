# CoreMasterKB v1.2 Retrieval View 架构方案

- 日期：2026-04-22
- 作者：Codex
- 状态：讨论收口稿
- 适用范围：`knowledge_mining` + `agent_serving` + `llm_service`

## 1. 背景

基于最新提交、当前实现和 `.dev` 下的讨论文档，CoreMasterKB 已完成：

- `llm_service` 统一调用运行时的 final contract 收口
- `knowledge_mining` 的 segment / enrich / relations / retrieval_units 基础骨架
- `agent_serving` 的 planner / retriever / fusion / reranker / assembler 基础骨架

但系统当前仍停留在“能跑通”的阶段，尚未进入“真正可用”的阶段。根因不是单点 bug，而是 Mining 与 Serving 之间的中间层合同尚未稳定。

当前最核心的问题是：

- Serving 检索命中的是 `retrieval_unit`
- 证据下钻、关系扩展、上下文组装依赖的是 `raw_segment`
- 但数据库模型里还没有一条稳定、强约束的一等桥接关系，把 `retrieval_unit` 明确锚定回 `raw_segment`

因此，下一阶段的目标不应定义为“继续补功能”，而应定义为：

**正式建立 Retrieval View Layer。**

## 2. 长期架构定位

本方案不是终局工业级形态，而是 v1.2 的正式收口基线。其目标是在不堵死未来演进的前提下，使当前系统从“跑通”进入“可用”。

建议长期架构分为 5 层：

| 层 | 角色 | 当前职责 |
|---|---|---|
| L0 Content Truth Layer | 内容真相层 | `raw_segment` + `raw_segment_relations` |
| L1 Retrieval View Layer | 检索视图层 | `retrieval_unit`、后续 `generated_question / summary / contextualized unit / community unit` |
| L2 Retrieval Execution Layer | 检索执行层 | lexical / vector / graph retrieval + fusion + rerank |
| L3 Intelligence Layer | 智能增强层 | Mining enrich、Serving query understanding、LLM generation / rerank |
| L4 Evaluation & Governance Layer | 评估治理层 | golden set、检索指标、质量门禁、发布验证 |

当前 v1.2 的重点是正式建立 L1，并打通 L0 <-> L1 <-> L2 的主路径。

## 3. 工业级对齐原则

本方案对齐 2025-2026 工业级 RAG / Graph-RAG 的共同趋势，但不一次性引入过重复杂度。

### 3.1 已对齐的主线

- Query Understanding -> Retrieval -> Fusion -> Rerank -> Context Assembly -> LLM
- Document Parse -> Segment -> Enrich -> Relations -> Retrieval Views -> Serve
- sparse + dense + graph 三路并存，而非单路替代
- retrieval object 与 evidence object 分层，而非混用

### 3.2 当前不直接进入的重能力

这些方向是长期正确路线，但不应成为 v1.2 第一阶段阻塞项：

- 向量检索正式落地
- Cross-Encoder rerank
- discourse relations / RST
- parent-child retrieval hierarchy 完整实现
- community summary / GraphRAG 全局搜索
- 评估平台全量自动化

v1.2 应先修正当前最影响可用性的基础合同，再进入这些增强项。

## 4. 核心架构判断

### 4.1 `raw_segment` 是内容真相源

`raw_segment` 必须继续作为：

- 原始证据承载体
- 图扩展节点
- 关系网络的稳定锚点

`raw_segment_relations` 继续挂在 `raw_segment` 上，不迁移到 `retrieval_unit`。

### 4.2 `retrieval_unit` 是检索视图

`retrieval_unit` 的职责是：

- 面向召回和排序
- 承载不同粒度、不同表达方式、不同智能增强结果的检索视图
- 允许未来逐步扩展更多 `unit_type`

这意味着 `retrieval_unit` 不是“永远等同于一个 raw segment 的浅拷贝”，而是一个可持续演进的 retrieval projection。

### 4.3 必须建立强桥接

Serving 的 source drill-down、graph expansion、evidence packing 不能长期依赖解析弱 JSON 结构猜测来源。主路径必须从“弱解析”升级为“强关系 + 弱扩展”。

因此建议：

- 在 `asset_retrieval_units` 上新增强桥接字段 `source_segment_id`
- `source_refs_json` 保留，但退回为 provenance / 多源扩展信息

## 5. v1.2 Retrieval View 合同

### 5.1 数据模型变更

建议对 `asset_core` 做最小必要 schema 变化：

| 表 | 变更 | 原因 |
|---|---|---|
| `asset_retrieval_units` | 新增 `source_segment_id TEXT NULL REFERENCES asset_raw_segments(id)` | 建立 retrieval view 到 content truth 的一等桥接 |
| `asset_retrieval_units` | 为 `source_segment_id` 建索引 | Serving 下钻和 graph expansion 主路径需要 |

### 5.2 为什么需要新增字段

当前只靠 `source_refs_json` 会带来以下问题：

- JSON 结构弱约定，跨模块容易漂
- 无法通过强 schema 和 index 稳定支持 join / query / debug
- Serving 每增加一种 `unit_type` 都要继续扩展解析特例
- graph expansion 的 seed 入口不够刚性

`source_segment_id` 的语义应定义为：

**retrieval unit 的 primary source anchor，不代表唯一来源。**

因此：

- 单一来源靠 `source_segment_id`
- 多来源 / offsets / supporting refs 继续走 `source_refs_json`

### 5.3 `source_refs_json` 的保留语义

`source_refs_json` 不删除，但明确降级为扩展 provenance：

- `raw_segment_ids`
- offsets
- future section / document / community source refs
- multi-source support refs

Serving 的主消费优先级调整为：

1. `source_segment_id`
2. `source_refs_json.raw_segment_ids`
3. `target_ref_json`
4. 弱兜底逻辑

## 6. Retrieval Unit 类型收口

v1.2 第一阶段不建议把 unit 类型扩得过多。应先把现有类型收口成可用形态。

### 6.1 建议保留的主类型

| `unit_type` | v1.2 结论 |
|---|---|
| `raw_text` | 保留，作为 canonical retrieval seed |
| `contextual_text` | 暂保留，但视为过渡形态，不作为长期主力 |
| `entity_card` | 保留，但必须增强内容质量 |
| `generated_question` | 转入正式 LLM 路径，作为第一批智能增强视图 |
| `summary` | 保留 schema 位，但不作为 v1.2 第一阶段主线 |

### 6.2 当前不建议直接做的事

| 方向 | 原因 |
|---|---|
| 一次性引入大量新 `unit_type` | 会继续稀释跨模块合同 |
| 立刻删除 `contextual_text` | 当前 Serving 仍可能依赖旧行为，建议先降级处理 |
| 把 relations 挂到 retrieval unit | 会破坏 truth / view 分层 |
| 用 JSON 替代强桥接字段 | 不利于长期维护和工业级演进 |

## 7. FTS / BM25 的定位

`asset_retrieval_units_fts` 必须保留。

### 7.1 原因

FTS/BM25 不是临时能力，而是长期 sparse retrieval 通道：

- 对命令名、参数名、术语、缩写的精确词项匹配很强
- 冷启动阶段可用性高
- 易解释、易调试、易验证
- 未来可与 vector / graph 并存，而非被替代

### 7.2 v1.2 的正确定位

FTS 不迁移到 `raw_segment`，而继续建在 `retrieval_unit` 上。

因为长期上：

- `raw_segment` 是 truth layer
- `retrieval_unit` 是 retrieval view layer
- lexical retrieval 本来就应检索 retrieval view

### 7.3 v1.2 必做修正

| 模块 | 必做修正 |
|---|---|
| Mining | `search_text` 改为 jieba 预分词写入 |
| Serving | FTS query 从 phrase 改为 OR 语义 |
| Serving | normalizer 改 jieba 分词 |

## 8. Mining v1.2 职责

Mining 下一阶段的职责不是“继续堆 retrieval unit 类型”，而是把 Retrieval View Layer 的生产合同立稳。

### 8.1 必做项

| 优先级 | 事项 |
|---|---|
| P1 | `build_retrieval_units()` 能拿到真实 `raw_segment_id` 并写入 `source_segment_id` |
| P1 | `source_refs_json` 至少稳定写出 `raw_segment_ids` |
| P1 | `search_text` 改为 jieba 预分词 |
| P1 | `generated_question` 接入真实 `LlmQuestionGenerator` |
| P1 | `QuestionGenerator` 与 `llm_service` final contract 对齐 |

### 8.2 同期加固项

| 优先级 | 事项 |
|---|---|
| P2 | `entity_card` 丰富化，不再只写 name/type/section |
| P2 | `same_section` 加 distance 上限，避免 O(n^2) 爆炸 |
| P2 | `validate_build` 做成真实校验 |
| P2 | UPDATE 场景清理旧 segments / relations / retrieval_units |
| P2 | enrich 升级为 batch-capable 接口，支撑后续 LLM 实现 |

### 8.3 LLM 接入位点

Mining 侧优先接入：

1. `generated_question`
2. `EntityExtractor`
3. `RoleClassifier`

其中：

- `generated_question` 是第一优先级
- `enrich` 的 LLM 化在接口上要支持 batch / context aware，而不是继续逐 segment 强行调用

## 9. Serving v1.2 职责

Serving 下一阶段的重点不是先冲多路召回，而是把“单路 lexical retrieval + graph expansion”做成真正可用的基线。

### 9.1 必做项

| 优先级 | 事项 |
|---|---|
| P1 | source drill-down 优先走 `source_segment_id` |
| P1 | FTS query 改 OR 语义 |
| P1 | normalizer 改 jieba 分词 |
| P1 | 对 `raw_text / contextual_text` 做重复压制 |

### 9.2 同期优化项

| 优先级 | 事项 |
|---|---|
| P2 | 低价值 heading/TOC/link 做降权 |
| P2 | 在现有 reranker 插槽中补 rule rerank 策略 |
| P2 | build scope 下 source attribution 继续收紧与验证 |

### 9.3 LLM 接入顺序

Serving 建议按如下顺序引入 LLM：

1. query understanding / rewrite
2. planner enrichment
3. rerank
4. compression / summarization

不建议在 retrieval view 合同未稳定前，先以 LLM rerank 作为第一波主线。

## 10. `llm_service` 在 v1.2 的角色

当前 `llm_service` 已具备作为统一运行时基线的条件。v1.2 的要求不是再改对外接口，而是让 Mining / Serving 都按这版稳定 contract 接入。

### 10.1 Mining 调用模式

- 批量异步：`submit + poll`
- 适用：`generated_question`、segment enrich、future summary

### 10.2 Serving 调用模式

- 在线同步：`execute`
- 适用：query understanding、planner enrichment、future rerank

### 10.3 约束

- Mining / Serving 的调用面应视为冻结合同
- LLM Runtime 后续仅允许内部演进，不得再将变化扩散给调用方

## 11. v1.2 不做什么

为避免方案失控，v1.2 第一阶段明确不做：

- vector retrieval 正式落地
- multi-retriever full parallel rollout
- Cross-Encoder rerank 正式接入
- GraphRAG 社区摘要
- retrieval hierarchy 专门桥接表
- discourse relation 生产线
- 全量评估平台实现

这些都属于 v1.3+ 的自然演进项，而不是 v1.2 第一阶段的必需前提。

## 12. 长期工业级演进路线

### 12.1 v1.2

目标：从“跑通”进入“可用”

- 建立 Retrieval View Layer
- 建立 `source_segment_id` 强桥接
- lexical retrieval 中文可用
- LLM 开始进入 `generated_question` / enrich / query understanding

### 12.2 v1.3

目标：从“可用”进入“更好用”

- vector retrieval
- RRF / hybrid retrieval
- richer entity_card / summary
- better rerank
- parent-child retrieval view

### 12.3 v1.4+

目标：进入更完整的工业级知识检索后端

- discourse relations / RST
- community / section summaries
- GraphRAG local/global patterns
- evaluation & governance automation
- production-grade retrieval quality loop

## 13. 验收标准

本方案收口后，v1.2 第一阶段至少应满足：

| 能力 | 验收标准 |
|---|---|
| Retrieval bridge | retrieval unit 能稳定回到 raw segment |
| Source drill-down | Serving 不依赖弱 JSON 才能完成主路径 |
| Graph expansion | graph expansion 在 active build 下真实可用 |
| Chinese retrieval | 中文 query 不再因 phrase / 无分词而大面积失效 |
| LLM integration | `generated_question` 和 Serving query understanding 能按统一 runtime 接入 |
| Extensibility | schema 与 pipeline 不阻塞 future vector / graph / rerank / summary |

## 14. 最终建议

下一阶段不应定义为“继续补 Mining 和 Serving 功能”，而应定义为：

**正式建立 CoreMasterKB 的 Retrieval View Layer。**

其核心收口为：

- `raw_segment` 作为 truth layer
- `retrieval_unit` 作为 retrieval view layer
- `source_segment_id` 作为一等桥接
- `source_refs_json` 作为扩展 provenance
- FTS 保留为 sparse retrieval index
- LLM 按统一 runtime contract 开始接入 Mining / Serving 的正式 pipeline

这是当前从“跑通”进入“可用”最关键的一步，同时也不会堵死未来走向“好用、方便用、工业级多路检索”的长期演进路线。
