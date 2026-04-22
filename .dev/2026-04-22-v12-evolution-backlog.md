# v1.2 演进待办

> 本文档记录 v1.1 实现阶段发现的所有待改进项，作为后续演进的输入。
> 来源：逐阶段代码审查 + 数据库表逐张审查 + 管理员讨论。

- 创建时间：2026-04-22
- 最后更新：2026-04-22

---

## 一、架构级改进（影响数据模型或 pipeline 接口）

### EVO-01: document_key 生成策略改进

**现状：** `document_key = "doc:/{relative_path}"`，基于文件相对路径。

**问题：**
- 不同产品的同名文件（如 `commands/overview.md`）分批处理时 document_key 冲突
- 文件改名后身份丢失，产生孤儿 document
- 换输入目录可能导致不同文档被当成同一个

**场景：**
1. 官方统一构建：多产品文档目录结构相同，分批跑时 key 冲突
2. 文件重命名：同一文档改名后变成新 document

**建议方案：**
- `run()` 增加 `namespace` 参数：`doc:/{namespace}/{relative_path}`
- 或支持文档内嵌 ID（frontmatter `doc_id`）作为身份
- 或 scope + 文件名组合

**优先级：** HIGH（场景 1 直接阻塞多产品构建）

---

### EVO-02: 删除文件检测（REMOVE 语义）

**现状：** `classify_documents()` 有 REMOVE 分支但从未触发。pipeline 只扫描当前目录，不知道哪些文件被删了。

**问题：**
- 用户删除文件后重跑，旧文档仍在 active build 中被 Serving 返回
- incremental build 的 carry forward 会把已删除文档继承到新 build

**建议方案：**
- 在 `classify_documents()` 中对比 prev build 的 snapshots 与本次 snapshot_decisions
- prev build 中有但本次没有的 document → 标记 REMOVE
- 约 15 行代码

**优先级：** HIGH（阻塞用户个人知识库演进场景）

---

### EVO-03: scope 提升为一等实体

**现状：** scope_json 只是一个 JSON 字段，挂在 snapshot 和 link 上。不是表，没有唯一键。

**问题：**
- 无法按 scope 高效查询（JSON LIKE 性能差）
- scope 在 snapshot 上可能导致共享场景下的值冲突
- 无法做"这个设备型号下有多少知识"的精确统计

**建议方案：**
- 新建 `asset_scopes` 表：`id, scope_type, scope_value`
- document 关联 scope_id
- retrieval_units 上的 facets_json 可加 scope_id 方便过滤

**优先级：** MEDIUM（当前单设备场景够用，多设备/多产品时必需）

---

### EVO-04: document_type 自动分类

**现状：** `document_type` 始终为 NULL。`BatchParams.default_document_type` 默认 None，`RawFileData` 也没有此字段。

**问题：**
- Serving 层无法按文档类型过滤（command / feature / procedure 等）
- 已定义了 13 种合法值但从未使用

**建议方案：**
- v1.2 enrich 阶段基于文档内容（section title 模式、命令密度）自动分类
- 或 ingest 阶段从目录结构推断（如 `commands/` 目录下 → command 类型）

**优先级：** MEDIUM

---

## 二、Pipeline 阶段级改进

### EVO-05: Relations same_section O(n²) 爆炸

**位置：** `relations/__init__.py` 第 82-89 行

**现状：** 同一 section 下所有 segment 两两建关系。

**问题：** 大 section（如参数表）下 100 个 segment → 4950 条关系。

**建议方案：** 加 distance 上限（如 ≤ 5），只对近距离 segment 建 same_section 关系。

**优先级：** HIGH（大文档性能问题）

---

### EVO-06: Build validate 空操作

**位置：** `publishing/__init__.py` 第 143 行

**现状：** `update_build_status(build_id, "validated")` 无任何前置检查。

**问题：** 空 build 也能通过验证。

**建议方案：**
- 检查 build 至少有 1 个 active snapshot
- incremental build 的 parent build 必须存在
- snapshot_id 引用有效

**优先级：** HIGH（数据正确性）

---

### EVO-07: Snapshot 复用与 Segments 一致性

**位置：** `snapshot/__init__.py` + `jobs/run.py`

**现状：** run.py 的 SKIP 分支覆盖了内容不变场景。但 UPDATE 场景下旧 segments 可能残留。

**问题：** 同一 snapshot_id 下可能存在新旧两组 segments。

**建议方案：** UPDATE 场景下写入新 segments 前清理该 snapshot_id 下的旧数据。

**优先级：** MEDIUM（当前 SKIP 分支已覆盖主路径）

---

### EVO-08: Enrich batch 语义

**位置：** `enrich/__init__.py`

**现状：** `enrich()` 逐 segment 处理，无法利用前后 segment 上下文。

**问题：** LLM 实现通常需要 batch + context window。

**建议方案：** `Enricher` Protocol 增加 `enrich_batch(segments, **kwargs)` 方法，允许实现者一次性处理所有 segments。

**优先级：** MEDIUM（v1.2 LLM 接入时必需）

---

## 三、数据质量改进

### EVO-09: mining_runs 计数不准确

**位置：** `jobs/run.py` → `complete_run()`

**现状：**
- `new_count` = `committed_count`（没有区分新增 vs 更新）
- `updated_count` 永远为 0
- `skipped_count` 混合了内容未变 SKIP 和解析失败 SKIP

**建议方案：** 在 run.py 循环中区分 NEW/UPDATE/SKIP 计数，分别传入 complete_run。

**优先级：** LOW

---

### EVO-10: normalized_text 归一化策略不统一

**位置：** `segmentation/__init__.py` 第 187 行

**现状：** segment 的 `normalized_text = raw_text.lower().strip()`，只有小写+去首尾空白。

**问题：** 和 `hash_utils.py` 的 conservative normalization（CRLF→LF + 去尾空白 + 去空行）不一致。没有标点归一化、全角半角统一。

**建议方案：** 统一使用 hash_utils 的归一化逻辑，或建立单独的 normalize_text 工具函数。

**优先级：** LOW

---

### EVO-11: heading_role 与 semantic_role 体系重叠

**位置：** `enrich/__init__.py`

**现状：** `_classify_heading_role()` 输出到 `metadata.heading_role`，`DefaultRoleClassifier` 输出到 `semantic_role`。两套分类体系可能产生冲突（如 heading_role="parameter_definition" 但 semantic_role="unknown"）。

**建议方案：** 统一为一套分类体系，或在 enrich 中让 heading_role 影响语义角色分类。

**优先级：** LOW

---

## 四、边界能力

### EVO-12: 多 paragraph 合并无上限

**位置：** `segmentation/__init__.py`

**现状：** 连续 paragraph 全部合并到一个 segment，没有 token 上限。

**问题：** 10 段连续段落会生成超大 segment。

**建议方案：** 加 token 上限（如 500 token），超出则拆分。

**优先级：** LOW（网络设备文档以 table/code/list 为主，影响有限）

---

### EVO-13: entity_card 去重范围是单文档

**位置：** `retrieval_units/__init__.py`

**现状：** `seen_entity_cards` 是内存 set，只在单次 `build_retrieval_units` 调用内去重。

**问题：** 同一 entity 在不同文档中会各建一张 card。

**建议方案：** v1.3 跨文档 entity 合并时，在 build 级别做全局去重。

**优先级：** LOW（v1.3 范围）

---

### EVO-14: CJK token 估算不准确

**位置：** `parsers/__init__.py` PlainTextParser + `text_utils.py`

**现状：** `token_count()` 按空格分割估算，CJK 文本没有空格会严重低估。

**建议方案：** 使用字符级别估算（CJK 字符 1 字符 ≈ 1-2 token），或引入 jieba/ICU 分词。

**优先级：** LOW

---

### EVO-15: 嵌套列表子级丢失

**位置：** `structure/__init__.py`

**现状：** `_tokens_to_blocks()` 只取 depth==1 的 inline，嵌套列表子项被丢弃。

**建议方案：** 递归解析嵌套列表，保留层级结构到 structure_json。

**优先级：** LOW（网络设备文档嵌套列表少）

---

### EVO-16: html_table 不提取结构

**位置：** `structure/__init__.py`

**现状：** 检测到 `<table` 但只存原文，不提取 columns/rows。

**建议方案：** 使用简易 HTML parser 提取表格结构，或转为 Markdown table 后统一处理。

**优先级：** LOW

---

## 五、语篇关系（Discourse Relations / RST）

> 本节记录段落级语篇关系的设计方向。区别于实体级本体（ontology），当前聚焦段落之间的修辞/语义关联。
> 本体（实体-关系-实体三元组）是下一阶段的任务。

### EVO-17: 语篇关系标签空间（Label Space）

**背景：**

当前 `asset_raw_segment_relations` 的 relation_type CHECK 约束已预留 5 种语义关系：
`references / elaborates / condition / contrast / other`

但这是粗粒度的。需要定义完整的语篇关系标签空间。

**工业界现状：**
- Microsoft GraphRAG、LightRAG、Neo4j 全部是**实体级关系**，没有做段落级语篇关系
- **Disco-RAG**（2025/2026，萨尔大学/腾讯）是首个把 RST 语篇关系集成到 RAG 的完整框架，在 Loong/ASQA/SciNews 三个 benchmark 上全面超越 Microsoft GraphRAG
- 原始 RST（Mann & Thompson 1988）定义了 24 种关系
- RST Discourse Treebank 扩展为 78 种（16 组）
- eRST（Zeldes 2025）引入图论理论，45 个子类
- UniRST（2025）统一 11 种语言的 18 个树库

**建议标签空间（参考 Disco-RAG 验证的 inter-chunk 关系集）：**

#### 核心-从属关系（非对称，有方向）

| 关系类型 | 含义 | 中文含义 | 网络设备文档场景示例 |
|----------|------|----------|---------------------|
| `ELABORATES` | B 详细阐述 A | 阐述 | "ADD NE 命令用于添加网元" → 详细的参数说明 |
| `EVIDENCES` | B 为 A 提供证据/支撑 | 佐证 | "该功能可提升性能" → 性能测试数据表格 |
| `CAUSES` | B 导致 A | 原因 | "License 未激活" → "命令执行失败" |
| `RESULTS_IN` | A 导致 B | 结果 | "执行 ADD NE" → "网元被添加到系统中" |
| `BACKGROUNDS` | B 为 A 提供背景 | 背景 | "NE 是网络基本管理单元" → "ADD NE 命令说明" |
| `CONDITIONS` | B 是 A 的前提条件 | 条件 | "需先配置 NE 模板" → "ADD NE 命令" |
| `SUMMARIZES` | B 总结 A | 总结 | 一组命令说明 → 命令速查表 |
| `JUSTIFIES` | B 为 A 提供理由 | 理由 | "建议使用批量配置" → "批量配置效率提升 10 倍" |
| `ENABLES` | B 使 A 中的操作成为可能 | 使能 | "开启高级模式" → "MOD NE 高级参数" |

#### 多核心关系（对称）

| 关系类型 | 含义 | 中文含义 | 网络设备文档场景示例 |
|----------|------|----------|---------------------|
| `CONTRASTS_WITH` | A 和 B 观点/描述对比 | 对比 | "参数范围 1-100" vs "特定模式下 1-50" |
| `PARALLELS` | A 和 B 提出平行/相似论点 | 类比 | ADD NE 和 DELETE NE 的类似参数结构 |
| `SEQUENCES` | B 在时间/逻辑上跟随 A | 时序 | "步骤1: 配置 IP" → "步骤2: 配置路由" |

#### 否定关系

| 关系类型 | 含义 |
|----------|------|
| `UNRELATED` | 段落间未发现语篇联系 |

**与当前 schema 的映射：**
- 当前 schema 已有：`references` → 可映射为 `BACKGROUNDS` 或 `ELABORATES`
- 当前 schema 已有：`elaborates` → 直接对应 `ELABORATES`
- 当前 schema 已有：`condition` → 直接对应 `CONDITIONS`
- 当前 schema 已有：`contrast` → 直接对应 `CONTRASTS_WITH`
- 当前 schema 已有：`other` → 保留为 fallback

**建议：** 扩展 relation_type CHECK 约束，加入上述完整标签集。需要 ALTER TABLE 或新 schema 版本。

**优先级：** HIGH（v1.2 LLM 阶段核心增值）

---

### EVO-18: 语篇关系提取方法

**背景：** 当前 v1.1 的结构关系（previous/next/same_section 等）是规则生成的。v1.2 的语篇关系需要 LLM 判断。

**SOTA 方法：**

#### 方法 A: 零样本 LLM 提取（Disco-RAG 验证，推荐）

Disco-RAG 使用零样本提示，无需训练：
- Llama-3.3-70B 零样本在 RST-DT benchmark 达到 relation F1 = 58.6（微调模型 60.0）
- 8B 模型也能产生有用的语篇结构
- 消融实验：移除段落间语篇图谱，性能下降 4.97 分

提示策略：
```
给定一组段落，对每一对段落判断语篇关系。
可选关系类型：ELABORATES / EVIDENCES / CAUSES / RESULTS_IN /
BACKGROUNDS / CONDITIONS / SUMMARIZES / JUSTIFIES / ENABLES /
CONTRASTS_WITH / PARALLELS / SEQUENCES / UNRELATED

输出 JSON:
{
  "pairs": [
    {"source": "SEG_3", "target": "SEG_5", "relation": "CONDITIONS", "confidence": 0.92},
    {"source": "SEG_3", "target": "SEG_7", "relation": "ELABORATES", "confidence": 0.85},
    {"source": "SEG_3", "target": "SEG_12", "relation": "UNRELATED", "confidence": 0.95}
  ]
}
```

优化策略（控制 LLM 调用量）：
- 只对同一 section 内或相邻 section 的段落对做判断（不需要全量 O(n²)）
- 滑动窗口：每次传入 10-20 个段落，而非全文档
- 基于 same_section / previous / next 结构关系预筛选候选对

#### 方法 B: 微调小模型

- DMRST（Liu 2021）：BERT 编码器端到端 RST 解析
- Maekawa（EACL 2024）：Llama 2 70B + QLoRA 微调，达到 SOTA
- 自下而上策略优于自上而下（58.1 vs 55.2 F1）

#### 方法 C: 混合（推荐 v1.2）

- 结构关系（v1.1 规则生成）→ 预筛选候选段落对
- LLM 判断候选对之间的语篇关系类型
- 写入同一张 `asset_raw_segment_relations` 表，用 relation_type 区分层级

**优先级：** HIGH（v1.2 核心）

---

### EVO-19: 语篇关系在检索中的使用

**语篇关系的三个直接用途：**

#### 用途 1: 检索后证据扩展

检索到一条知识后，沿语篇边拉取支撑上下文：

```
用户问: "ADD NE命令怎么用？"
  → 检索到 segment S1（ADD NE 命令说明）
  → 沿 ELABORATES 边找到 S2（ADD NE 详细参数表）
  → 沿 CONDITIONS 边找到 S3（前置条件：需激活 License）
  → S1 + S2 + S3 一起送入 LLM 生成，答案更完整
```

实现方式：Serving 层查询时，对命中的 retrieval_units，沿 `asset_raw_segment_relations` 做图遍历：
```sql
-- 找到命中段落的支撑上下文
SELECT r.relation_type, r.confidence, seg.raw_text
FROM asset_raw_segment_relations r
JOIN asset_raw_segments seg ON seg.id = r.target_segment_id
WHERE r.source_segment_id = 'S1'
  AND r.relation_type IN ('ELABORATES', 'EVIDENCES', 'CONDITIONS', 'BACKGROUNDS')
ORDER BY r.confidence DESC;
```

#### 用途 2: 冲突检测与消歧

`CONTRASTS_WITH` 标记矛盾信息，避免 LLM 错误合并：

```
S4: "该参数取值范围 1-100"
S5: "该参数在特定模式下取值范围 1-50"
→ CONTRASTS_WITH 关系
→ Serving 层告诉 LLM："这两条信息存在对比关系，请区分条件"
```

Disco-RAG 案例验证：当 Chunk A 说"12% lower incidence"而 Chunk B 说"no significant overall effect"时，Contrast 关系阻止 LLM 过度泛化。

#### 用途 3: 上下文窗口优化

- 有语篇关系的段落（ELABORATES、EVIDENCES）优先一同放入 context
- UNRELATED 的段落即使在同一 section 也降权
- Disco-RAG 在 40% 检索噪声下仍保持强劲（LLM Score 56.17 vs 标准 RAG 45.23）

**与当前 asset_raw_segment_relations schema 的兼容性：**
- `weight` 字段：结构关系固定 1.0，语篇关系可用 LLM confidence 填充
- `confidence` 字段：规则生成固定 1.0，LLM 生成可变（0.0~1.0）
- `distance` 字段：语篇关系通常为 NULL（不基于位置）
- `metadata_json`：可存储 LLM 推理依据、信号词等

**优先级：** HIGH（v1.2 Serving 层增值）

---

### EVO-20: 语篇关系建在 segments 上而非 retrieval_units 上

**设计决策：** 语篇关系建在 `asset_raw_segments` 之间，不在 `asset_retrieval_units` 之间。

**理由：**
- retrieval_units 是 segments 的投影/视图（raw_text 1:1, contextual_text 1:1, entity_card N:1, generated_question 1:1）
- 语篇关系是内容属性（"S3 阐述了 S5"），不是检索属性
- entity_card 和 generated_question 是索引产物，在它们之间建语篇关系无语义意义
- 在 segments 上建一次关系，所有类型的 retrieval_units 都能通过 segment 桥接使用

**需要配套改动：**
- `asset_retrieval_units` 表增加 `source_segment_id TEXT REFERENCES asset_raw_segments(id)` 字段
- Serving 层图遍历路径：`unit → segment → relations → related_segments → raw_text units`
- 避免 JSON 解析，直接外键 JOIN

**优先级：** HIGH（v1.2 架构决策）

---

### 参考资源

#### 核心论文

| 资源 | 说明 |
|------|------|
| [Disco-RAG: Discourse-Aware Retrieval-Augmented Generation](https://arxiv.org/html/2601.04377v5) | 首个将 RST 语篇关系集成到 RAG 的完整框架，三个 benchmark SOTA |
| [Disco-RAG (OpenReview)](https://openreview.net/forum?id=AWv0mlCeUk) | 同上，OpenReview 版本 |
| [RST 原始论文关系定义 (SFU)](https://www.sfu.ca/rst/01intro/definitions.html) | Mann & Thompson 1988 定义的 24 种 RST 关系 |
| [eRST: A Signaled Graph Theory (ACL 2025)](http://aclanthology.org/2025.cl-1.3/) | Zeldes 2025，引入图论理论，45 子类 + 信号分类法 |
| [UniRST: Bridging Discourse Treebanks (CODI 2025)](https://aclanthology.org/2025.codi-1.17/) | 统一 11 种语言的 18 个 RST 树库 |
| [LLM-based RST Parsing (EACL 2024)](https://www.aclanthology.org/2024.eacl-long.171/) | Llama 70B + QLoRA 微调 RST 解析 SOTA |
| [Llamipa: Incremental SDRT Parsing (EMNLP 2024)](https://aclanthology.org/2024.findings-emnlp.373.pdf) | 增量式语篇图谱解析 |
| [AAAI 2025: Implicit Discourse Relation Recognition](https://ojs.aaai.org/index.php/AAAI/article/view/40634/44595) | 隐式语篇关系识别 |

#### 工业实现参考

| 资源 | 说明 |
|------|------|
| [Microsoft GraphRAG](https://microsoft.github.io/graphrag/) | 实体级 KG + 社区摘要，**无语篇关系** |
| [Microsoft GraphRAG (GitHub)](https://github.com/microsoft/graphrag) | 开源实现 |
| [GraphRAG Patterns Catalog](https://graphrag.com/reference/) | Neo4j 维护的 GraphRAG 模式目录 |
| [Lexical Graph + Sibling Structure](https://graphrag.com/reference/knowledge-graph/lexical-graph-sibling-structure/) | 只有 NEXT_CHUNK/PREVIOUS_CHUNK，无语篇关系 |
| [LightRAG (ACL 2025)](https://aclanthology.org/2025.findings-emnlp.568/) | 轻量实体级 KG，**无语篇关系** |
| [LightRAG 提取分析 (Neo4j Blog)](https://neo4j.com/blog/developer/under-the-covers-with-lightrag-extraction/) | LightRAG 内部机制 |
| [From Legal Documents to Knowledge Graphs (Neo4j)](https://neo4j.com/blog/developer/from-legal-documents-to-knowledge-graphs/) | 法律领域文档→KG |

#### 其他参考

| 资源 | 说明 |
|------|------|
| [GraphRAG Explained (GoPenAI)](https://blog.gopenai.com/graphrag-explained-from-knowledge-graph-construction-to-structured-llm-reasoning-05580549f84c) | GraphRAG 全流程解析 |
| [Harnessing Discourse Structure for Retrieval (OpenReview)](https://openreview.net/pdf?id=6h9Q6MMqen) | 语篇结构增强检索 |
| [Enhancing RAG with Discourse (Dialogue 2025)](https://dialogue-conf.org/wp-content/uploads/2025/06/GalitskyBIlvovskyDMorkovkinA.110.pdf) | 对话语篇增强 RAG |

---

## 六、检索单元构建方法（Retrieval Unit Construction）

> 本节记录 v1.2 检索单元构建的工业级参考方法。
> 当前 v1.1 实现了 4 种 retrieval unit 类型：raw_text、contextual_text、entity_card、generated_question。
> v1.2 需要在以下方向增强。

### EVO-21: 父子层级分块（Parent-Child Chunk Hierarchy）

**背景：**

当前 retrieval_units 是平铺的，所有 unit 独立检索。但文档天然有层级结构（section → subsection → paragraph）。

**SOTA 方法：LlamaIndex AutoMergingRetriever**

- 小 chunk 用于精确匹配，大 chunk（parent）用于上下文完整性
- 当一个 parent 下的 children 被大量命中时，自动合并为 parent chunk 送入 LLM
- 实测效果：+15.3% hit rate，+22.7% MRR（LlamaIndex 官方 benchmark）

**与当前系统的映射：**
- 当前 `asset_raw_segments` 已有 `section_path` 和 `section_title` 字段
- 可基于 section_path 构建 parent-child 关系
- 新增 `retrieval_unit` 类型：`parent_context`（section 级别的聚合文本）
- 需要新字段：`parent_unit_id` REFERENCES `asset_retrieval_units(id)`

**实现建议：**
```python
# 在 build_retrieval_units 阶段
for section_path, segments in group_by_section(all_segments):
    parent_unit = RetrievalUnitData(
        unit_type="parent_context",
        text="\n".join(s.raw_text for s in segments),
        target_ref_json={"section_path": section_path},
    )
    for child_segment in segments:
        child_unit = RetrievalUnitData(
            unit_type="raw_text",
            parent_unit_id=parent_unit.id,
            ...
        )
```

**参考：**
- [LlamaIndex AutoMergingRetriever](https://docs.llamaindex.ai/en/stable/examples/retrievers/auto_merging_retriever/)
- [Parent-Child Pattern (LangChain)](https://python.langchain.com/docs/modules/data_connection/retrievers/parent_document_retriever/)

**优先级：** HIGH（v1.2 检索质量核心提升）

---

### EVO-22: 上下文增强检索（Contextual Retrieval）

**背景：**

当前 `contextual_text` 类型的 retrieval unit 是基于 section title 拼接的前缀，信息量有限。

**SOTA 方法：Anthropic Contextual Retrieval**

- 对每个 chunk，使用 LLM 在文档全文上下文中生成一句上下文描述
- 将上下文描述拼接到原始 chunk 前，一起做 embedding 和 FTS 索引
- 实测效果：检索失败率降低 49%（Anthropic 官方报告）

**实现建议：**
```python
class Contextualizer(Protocol):
    def contextualize(self, chunk_text: str, full_document: str) -> str: ...

class LLMContextualizer:
    def contextualize(self, chunk_text, full_document):
        prompt = f"""<document>
{full_document}
</document>

这是 <document> 中的一个片段。请用一句话说明这个片段在文档中的位置和作用：

<chunk>
{chunk_text}
</chunk>

上下文描述："""
        return llm.generate(prompt)
```

- 利用 v1.1 已建立的 `QuestionGenerator` Protocol 模式
- 上下文描述写入 `asset_retrieval_units` 的 `text` 字段前缀
- FTS5 索引自动覆盖上下文描述

**参考：**
- [Anthropic: Contextual Retrieval](https://www.anthropic.com/research/building-effective-agents)
- [Contextual Retrieval Cookbook](https://github.com/anthropics/anthropic-cookbook/blob/main/skills/contextual-embeddings/)

**优先级：** HIGH（v1.2 与 LLM Runtime 集成的关键场景）

---

### EVO-23: 语义分块（Semantic Chunking）

**背景：**

当前 segmentation 是基于 Markdown 结构（heading、table、code block 等）硬切分的。纯文本文件或无结构文档无法有效分块。

**SOTA 方法：**

#### 方法 A: 嵌入断点检测（LlamaIndex SemanticSplitter）

- 对每个句子生成 embedding
- 计算相邻句子的余弦相似度
- 相似度低于阈值处断开（语义主题切换点）
- 阈值通常为 percentile=75（即低于 75 分位数的相似度处断开）

#### 方法 B: Late Chunking（Jina AI）

- 先对整个文档做 embedding
- 再在 embedding 空间中做分块
- 避免了"先分块再 embedding"的信息丢失
- 实测效果：+1.3 到 +6.5pp nDCG 提升（Jina AI benchmark）

**实现建议：**
- v1.2 优先实现方法 A（简单、可控）
- 新增 `SegmentationStrategy` Protocol：
  ```python
  class SegmentationStrategy(Protocol):
      def segment(self, text: str, metadata: dict) -> list[str]: ...
  ```
- 结构化文档继续用 `structure + segmentation`
- 纯文本文档用 `SemanticChunker`
- embedding 调用走 LLM Runtime

**参考：**
- [LlamaIndex SemanticSplitter](https://docs.llamaindex.ai/en/stable/examples/node_parsers/semantic_chunking/)
- [Jina AI Late Chunking](https://jina.ai/news/late-chunking-in-long-context-embedding-models/)
- [Semantic Chunking论文 (arXiv)](https://arxiv.org/abs/2405.11118)

**优先级：** MEDIUM（当前结构化文档已有良好分块，纯文本场景需此能力）

---

### EVO-24: 假设文档嵌入（HyDE）

**背景：**

当前检索是 query ↔ chunk 的直接匹配。用户查询和文档语言风格差异大时（如用户说"怎么配NE"但文档说"ADD NE 命令用于新增网元实例"），匹配效果差。

**SOTA 方法：HyDE（Hypothetical Document Embedding）**

- 先让 LLM 根据用户 query 生成一个"假设性答案"
- 用假设性答案的 embedding 去检索，而非原始 query
- 假设性答案的措辞更接近文档语言，匹配更准
- ACL 2023 论文：5-15% 检索提升

**实现建议：**
- 这是 **Serving 层**的能力，不影响 Mining pipeline
- 但 Mining 需要确保 retrieval_units 的 embedding 质量足够好
- 当前 FTS5 只支持文本匹配，HyDE 需要 embedding 检索 → 需要向量存储
- v1.2 可在 `asset_retrieval_embeddings` 表中预存 embedding
- Serving 层实现 HyDE 逻辑

**参考：**
- [HyDE: Precise Zero-Shot Search (ACL 2023)](https://arxiv.org/abs/2212.10496)
- [HyDE Implementation Guide](https://python.langchain.com/docs/integrations/retrievers/hyde/)

**优先级：** MEDIUM（需要 embedding infrastructure 先就位）

---

### EVO-25: 社区摘要（Community Summaries）

**背景：**

当知识库规模增大时，全量检索噪声增大。需要一种"概览级别"的知识组织方式。

**SOTA 方法：Microsoft GraphRAG 社区摘要**

- 将实体/段落图谱按社区检测算法分区（Leiden 算法）
- 对每个社区生成 LLM 摘要
- 查询时先匹配社区摘要，再在社区内精确检索
- 实测效果：72-83% comprehensiveness win rate（vs 简单 RAG）

**与当前系统的映射：**
- v1.2 的语篇关系（EVO-17~19）构建图谱后，可在此基础上做社区检测
- `retrieval_unit` 新增类型：`community_summary`
- `target_type` = `community`，`target_ref_json` 存社区 ID 和成员 segment 列表
- 社区摘要由 LLM 生成（利用 LLM Runtime）

**实现建议：**
- 依赖语篇关系图谱先建好
- 使用 networkx 的 community detection（Python 原生）
- 每个 community 生成摘要后作为 retrieval_unit 落库

**参考：**
- [Microsoft GraphRAG](https://microsoft.github.io/graphrag/)
- [GraphRAG Community Reports](https://microsoft.github.io/graphrag/posts/query/4-global_search/)
- [Leiden Algorithm](https://www.nature.com/articles/s41598-019-41695-z)

**优先级：** LOW（v1.3 范围，依赖语篇图谱先建好）

---

### EVO-26: 中文文本特殊处理

**背景：**

当前 token 估算、分块策略都是英文假设（空格分词、换行分段）。中文文本需要特殊处理。

**SOTA 方法：**

#### 分词

- **jieba**：最广泛使用的中文分词库，适合 FTS5 分词器
- **pkuseg**：北大分词，领域自适应更好
- FTS5 自定义分词器：将 jieba 分词结果以空格连接后写入 `search_text`

#### Embedding

- **BGE-M3**（BAAI）：多语言多功能 embedding 模型
  - 支持稠密检索 + 稀疏检索 + 多向量检索
  - 中文效果在 C-MTEB 排名靠前
  - 可通过 LLM Runtime 调用
- **text2vec-chinese**：轻量中文 embedding

#### 分块

- 中文段落边界：以句号、问号、感叹号为分隔
- 与 structure 的 heading 分块互补：heading 之间按句号细分为 sub-chunk

**实现建议：**
- `search_text` 生成时，对中文内容做 jieba 分词后空格连接
- token_count 估算对 CJK 字符用字符级别（1 CJK ≈ 1.5 token）
- embedding 模型选择 BGE-M3（与 LLM Runtime 集成）

**参考：**
- [BGE-M3 (HuggingFace)](https://huggingface.co/BAAI/bge-m3)
- [jieba 中文分词](https://github.com/fxsjy/jieba)
- [C-MTEB Benchmark](https://huggingface.co/spaces/mteb/leaderboard)

**优先级：** MEDIUM（网络设备文档中英混合，中文处理是刚需）

---

### EVO-27: FTS5 中文分词器增强

**背景：**

当前 FTS5 使用 `unicode61` tokenizer，不支持中文分词。中文查询只能全文匹配，无法按词检索。

**现状：**
- `unicode61` 对中文按字符分词（每个汉字一个 token）
- 搜索"业务感知"只能匹配精确连续的 4 个字
- 无法匹配"业务"单独检索"感知"

**建议方案：**

#### 方案 A: jieba 预分词 + 空格连接

- `search_text` 生成时用 jieba 分词，结果空格连接
- FTS5 仍用 `unicode61` tokenizer（按空格分词）
- 无需自定义 tokenizer，实现简单
- 示例：`"业务感知 是指 在用户会话 中"` → FTS5 索引 `["业务感知", "是指", "在", "用户", "会话", "中"]`

#### 方案 B: FTS5 自定义 tokenizer（jieba）

- 用 SQLite C extension 注册 jieba tokenizer
- FTS5 创建时 ` tokenize="jieba"`
- 更准确但实现复杂，需要编译 C 扩展

**推荐方案 A**（实现简单，效果足够）

**优先级：** MEDIUM（与 EVO-26 配套）

---

## 七、检索演进参考资源

### 检索单元构建

| 资源 | 说明 |
|------|------|
| [LlamaIndex AutoMergingRetriever](https://docs.llamaindex.ai/en/stable/examples/retrievers/auto_merging_retriever/) | 父子层级分块 + 自动合并 |
| [LangChain ParentDocumentRetriever](https://python.langchain.com/docs/modules/data_connection/retrievers/parent_document_retriever/) | Parent-Child 模式 |
| [Anthropic Contextual Retrieval](https://www.anthropic.com/research/building-effective-agents) | 上下文增强检索，49% 失败率降低 |
| [Contextual Retrieval Cookbook (GitHub)](https://github.com/anthropics/anthropic-cookbook/blob/main/skills/contextual-embeddings/) | Anthropic 官方实现示例 |
| [Semantic Chunking (arXiv)](https://arxiv.org/abs/2405.11118) | 基于语义断点的分块方法 |
| [Jina AI Late Chunking](https://jina.ai/news/late-chunking-in-long-context-embedding-models/) | 先 embedding 后分块 |
| [HyDE: Precise Zero-Shot Search (ACL 2023)](https://arxiv.org/abs/2212.10496) | 假设文档嵌入 |
| [HyDE Implementation (LangChain)](https://python.langchain.com/docs/integrations/retrievers/hyde/) | HyDE 实现指南 |
| [Microsoft GraphRAG](https://microsoft.github.io/graphrag/) | 社区摘要 + 全局检索 |
| [GraphRAG Community Reports](https://microsoft.github.io/graphrag/posts/query/4-global-search/) | 社区摘要具体实现 |

### 中文文本处理

| 资源 | 说明 |
|------|------|
| [BGE-M3 (HuggingFace)](https://huggingface.co/BAAI/bge-m3) | 多语言多功能 embedding 模型 |
| [jieba 中文分词](https://github.com/fxsjy/jieba) | 最广泛使用的中文分词库 |
| [C-MTEB Benchmark](https://huggingface.co/spaces/mteb/leaderboard) | 中文文本嵌入基准测试 |
| [text2vec-chinese](https://github.com/shibing624/text2vec) | 轻量中文 embedding |

---

## 已修复项（v1.1 阶段）

| 编号 | 问题 | 修复提交 |
|------|------|----------|
| FIX-01 | mining_runs.source_batch_id 为空 | batch_id 生成提前到 create_run 之前 |
| FIX-02 | mining_run_documents.started_at 为空 | register_document 时写入 started_at |
