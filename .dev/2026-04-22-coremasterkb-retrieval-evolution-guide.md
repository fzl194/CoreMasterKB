# CoreMasterKB 检索演进指导书

> **版本：** v1.0
> **日期：** 2026-04-22
> **状态：** 演进规划
> **适用范围：** Mining（检索单元构建）+ Serving（检索执行）
> **目标读者：** Mining 工程师、Serving 工程师、架构师

---

## 导读

本文档对 CoreMasterKB 检索系统的每一个技术维度做"当前实现 vs 工业最佳实践"的精确对比，明确差距和目标。不是泛泛的方向讨论，而是可落地的演进指导。

**职责分工原则：**
- **Mining** 侧负责：检索单元构建、分词、关系图谱、embedding、质量评估
- **Serving** 侧负责：查询理解、多路召回、融合、重排、上下文组装

---

## 一、总览：当前 vs 目标

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        工业级 RAG 全链路 (2025-2026)                      │
│                                                                          │
│  Query → [Query Understanding] → [Multi-path Retrieval]                 │
│            ├── HyDE / Multi-query          ├── BM25 (sparse, top-50)    │
│            ├── Intent detection             ├── Vector (dense, top-50)  │
│            ├── Entity extraction            ├── Graph (N-hop traversal) │
│            └── Synonym expansion            └── Community summary      │
│                                                                          │
│         → [RRF Fusion k=60] → [Cross-Encoder Rerank top-15]             │
│         → [MMR Diversity] → [Discourse Expansion] → LLM                 │
│                                                                          │
│  Mining 侧：                                                              │
│  Raw doc → Parse → Segment → Enrich → Relations → Retrieval Units       │
│             ├── 结构分块              ├── 语义角色        ├── 结构关系     │
│             └── 语义分块(optional)    ├── NER 实体       ├── 语篇关系     │
│                                          └── 上下文增强      └── 社区摘要   │
└──────────────────────────────────────────────────────────────────────────┘
```

**当前实现 vs 工业标准 9 维度对标：**

| # | 维度 | 当前状态 | 工业最佳实践 | 差距等级 |
|---|------|---------|-------------|---------|
| 1 | 文本分块 | Markdown 结构硬切分 | 结构分块 + 语义分块双轨 | MEDIUM |
| 2 | 中文文本处理 | 无分词，unicode61 按字符 | jieba 预分词 + unicode61 | **CRITICAL** |
| 3 | 检索单元类型 | 4 种平铺（raw/contextual/entity/question） | 父子层级 + 上下文增强 + 社区摘要 | HIGH |
| 4 | 关系图谱 | 仅结构关系（prev/next/same_section） | 结构关系 + 语篇关系（RST） | HIGH |
| 5 | 查询理解 | 规则分词 + 关键词匹配 | LLM 意图识别 + 实体抽取 + HyDE | HIGH |
| 6 | 检索通道 | FTS5 BM25 单路 | BM25 + Vector + Graph 三路 | HIGH |
| 7 | 融合与重排 | IdentityFusion + 规则偏好排序 | RRF + Cross-Encoder + MMR | HIGH |
| 8 | 图扩展 | BFS 已实现但因 contract 断裂未生效 | 语篇引导扩展 + 冲突检测 | **CRITICAL** |
| 9 | 评估体系 | 无 | RAGAS（50-200 golden set） | HIGH |

---

## 二、维度 1：文本分块（Segmentation）

### 2.1 当前实现

**Mining `segmentation/__init__.py`：**
- 基于 Markdown AST 结构硬切分：heading → 独立 segment，table/code/list → 独立 segment，paragraph → 合并
- 连续 paragraph 无上限合并（EVO-12）
- `token_count()` 按空格分割估算，CJK 文本严重低估（EVO-14）
- 嵌套列表子级丢弃（EVO-15）
- HTML table 不提取结构（EVO-16）

```python
# 当前切分逻辑（简化）
for block in section.blocks:
    if block.block_type == "heading":
        emit_segment(heading_segment)
    elif block.block_type in ("table", "code", "list"):
        emit_segment(block_segment)
    else:
        group.append(block)  # 连续 paragraph 合并
```

### 2.2 工业最佳实践

| 方法 | 来源 | 效果 | 适用场景 |
|------|------|------|---------|
| **结构分块** | LlamaIndex / LangChain | 精确保持文档结构 | Markdown/HTML 有结构文档 |
| **语义分块** | LlamaIndex SemanticSplitter | +15-20% 语义边界准确率 | 纯文本/无结构文档 |
| **Late Chunking** | Jina AI | +1.3~6.5pp nDCG | 长文档场景 |
| **父子层级** | LlamaIndex AutoMergingRetriever | +15.3% hit rate, +22.7% MRR | 需要上下文完整性的场景 |
| **递归字符分块** | LangChain RecursiveCharacterTextSplitter | 简单可靠 | 兜底方案 |

### 2.3 差距分析

| 方面 | 当前 | 目标 |
|------|------|------|
| 分块策略 | 单一结构切分 | 结构切分 + 语义切分双轨 |
| 段落合并 | 无上限 | token 上限 500，超出拆分 |
| CJK token 估算 | 空格分割（严重低估） | 字符级估算（1 CJK ≈ 1.5 token） |
| 嵌套结构 | 丢弃子级 | 递归保留层级 |
| 表格 | 存原文 | 提取 columns/rows 结构 |

### 2.4 演进目标

**Phase 1（v1.2 立行）：**
- 连续 paragraph 合并加 token 上限（500 token）
- CJK token 估算改字符级
- 修复嵌套列表丢失

**Phase 2（v1.2 LLM 集成）：**
- 新增 `SegmentationStrategy` Protocol，纯文本文档走语义分块
- 结构化文档继续用当前方式（已足够好）

**Phase 3（v1.3）：**
- Late Chunking（依赖 embedding 基础设施）

---

## 三、维度 2：中文文本处理

### 3.1 当前实现

**Mining 侧（`retrieval_units/__init__.py`）：**
- `search_text = seg.raw_text`（原文直存，无分词）
- FTS5 tokenizer = `unicode61`（对中文按字符逐字分词）
- "业务感知" 被索引为 `["业", "务", "感", "知"]`（4 个单字 token）

**Serving 侧（`bm25_retriever.py`）：**
- `_tokenize_for_fts()` 尝试 jieba 分词，但 ImportError 时回退原文
- `_escape_fts_query()` 用双引号包裹为短语查询，要求精确连续匹配
- "什么是业务感知" → jieba 切为 `["什么", "是", "业务", "感知"]` → 包裹为 `"什么 是 业务 感知"` → 要求 4 个词必须按顺序连续出现在索引中
- 但索引中每个字是独立 token → **永远匹配不上**

**Normalizer 侧（`normalizer.py`）：**
- `_extract_keywords()` 用 `re.split(r"[\s,，、？?。.！!]+", query)` 分词
- "什么是业务感知" 无分隔符 → 整串作为一个 token → 被 stopword 过滤（"是"无法移除）

### 3.2 工业最佳实践

| 环节 | 最佳实践 | 来源 |
|------|---------|------|
| **索引端分词** | jieba 预分词 + 空格连接写入 search_text | 所有中文检索系统标准做法 |
| **查询端分词** | jieba 分词后 OR 查询 | FTS5 最佳实践 |
| **FTS5 策略** | 索引 search_text（预分词）而非 text（原文） | SQLite FTS5 文档 |
| **Embedding** | BGE-M3（多语言，C-MTEB 靠前） | BAAI |
| **NER** | chinese-roberta-wwm-ext + BiLSTM + CRF | 学术 SOTA |

### 3.3 差距分析

| 方面 | 当前 | 目标 |
|------|------|------|
| 索引端分词 | 无（unicode61 逐字） | jieba 预分词，空格连接写入 search_text |
| 查询端分词 | 双引号短语查询（精确匹配） | OR 语义查询 |
| Normalizer | re.split 按标点分词 | jieba 分词 + stopword 过滤 |
| Embedding | 无 | BGE-M3（v1.2 向量检索时） |

### 3.4 演进目标（**最高优先级，阻塞所有中文检索**）

**Mining 侧改动（`retrieval_units/__init__.py`）：**

```python
# 当前
search_text = seg.raw_text

# 目标
import jieba
search_text = " ".join(jieba.cut(seg.raw_text))
# "业务感知是指在用户会话过程中..." → "业务 感知 是 指 在 用户 会话 过程 中 ..."
```

**Serving 侧改动（`bm25_retriever.py`）：**

```python
# 当前：短语查询（双引号包裹）
def _escape_fts_query(text: str) -> str:
    return '"' + text.replace('"', '""') + '"'

# 目标：OR 查询（每个 token 独立匹配）
def _build_fts_query(tokens: list[str]) -> str:
    # FTS5 OR 查询：每个 token 独立匹配，BM25 自动加权
    escaped = [t.replace('"', '""') for t in tokens if t.strip()]
    return " OR ".join(f'"{t}"' for t in escaped)
```

**Normalizer 改动：**

```python
# 当前
tokens = re.split(r"[\s,，、？?。.！!]+", cleaned)

# 目标：jieba 分词
import jieba
tokens = list(jieba.cut(cleaned))
tokens = [t for t in tokens if len(t) >= 2 or _is_cjk(t)]
```

---

## 四、维度 3：检索单元构建（Retrieval Units）

### 4.1 当前实现

**4 种类型，平铺独立：**

| 类型 | 生成方式 | 数量关系 | search_text | 问题 |
|------|---------|---------|-------------|------|
| `raw_text` | 直接复制 segment | 1:1 | `seg.raw_text` | 内容与 contextual_text 重叠 |
| `contextual_text` | `[section_path]` + raw_text | 1:1 | 同上 | 只是加了 section 前缀，信息增量小 |
| `entity_card` | `"entity_name (type) — 见 section_title"` | N:1 | `"entity_name entity_type"` | 内容太简短，检索价值低 |
| `generated_question` | 预留，v1.1 未实现 | 0 | N/A | 空 |

**关键缺陷：**
1. `raw_text` 和 `contextual_text` 内容高度重叠，导致检索结果重复
2. `contextual_text` 的上下文信息只是 section_path 文本拼接，不是 LLM 生成的语义上下文
3. `entity_card` 过于简短（如 `"SA (feature) — 见 业务感知概述"`），无法被有效检索
4. 无父子层级关系——一个大 section 下 20 个 segment，全部独立返回，无上下文聚合能力
5. `source_refs_json` 写入 `{document_key, segment_index, offsets}`，但 Serving 期望 `{raw_segment_ids}`

### 4.2 工业最佳实践

#### 4.2.1 父子层级分块（Parent-Child Chunk Hierarchy）

**来源：** LlamaIndex AutoMergingRetriever / LangChain ParentDocumentRetriever

**效果：** +15.3% hit rate, +22.7% MRR

**原理：**
- 小 chunk（child）用于精确匹配
- 大 chunk（parent）用于上下文完整性
- 当一个 parent 下多个 children 被命中时，自动合并为 parent 送入 LLM

```
Section: "ADD NE 命令说明"
├── Parent: 整个 section 文本（用于 LLM 上下文）
│   ├── Child 1: "ADD NE 命令用于添加网元..."（用于检索匹配）
│   ├── Child 2: 参数表（用于检索匹配）
│   └── Child 3: 示例（用于检索匹配）
```

#### 4.2.2 上下文增强检索（Contextual Retrieval）

**来源：** Anthropic Contextual Retrieval (2024)

**效果：** 检索失败率降低 49%

**原理：**
- 对每个 chunk，用 LLM 在全文上下文中生成一句描述
- 描述拼接到原始 chunk 前，一起做 FTS 索引和 embedding
- 解决"chunk 脱离原文语境后语义丢失"问题

```
# 当前 contextual_text
"[1.1.2 > ADD NE 命令] ADD NE 命令用于添加网元实例..."

# 目标 contextual_text（Anthropic 方式）
"本段位于 LTE 基站配置指南 > 网元管理章节，描述 ADD NE 命令的用法。
ADD NE 命令用于添加网元实例..."
```

#### 4.2.3 社区摘要（Community Summaries）

**来源：** Microsoft GraphRAG

**效果：** 72-83% comprehensiveness win rate

**原理：**
- 在语篇关系图谱上做社区检测（Leiden 算法）
- 每个社区生成 LLM 摘要
- 查询时先匹配社区摘要，再社区内精确检索

### 4.3 差距分析

| 方面 | 当前 | 目标 |
|------|------|------|
| 层级结构 | 平铺，无 parent-child | 父子层级，支持 auto-merge |
| 上下文增强 | section_path 文本拼接 | LLM 语义上下文描述 |
| entity_card | "name (type) — 见 title" | 实体属性 + 关联知识摘要 |
| generated_question | 空 | LLM 生成假设性问题（辅助检索） |
| 结果去重 | 无 | parent-child 去重 + unit_type 去重 |
| source_refs | `{document_key, segment_index}` | `source_segment_id` 外键 |

### 4.4 演进目标

**Phase 1（v1.2 立行，修复 contract）：**
- `source_refs_json` 增加 `raw_segment_ids` 字段，或直接加 `source_segment_id` 外键列
- 去掉 `contextual_text` 类型（与 raw_text 高度重叠，信息增量低）
- entity_card 改进：包含实体描述文本（从 enrich 阶段获取）

**Phase 2（v1.2 LLM 集成）：**
- 新增 `parent_context` 类型：section 级别聚合
- Anthropic contextual retrieval：LLM 生成上下文描述
- generated_question：LLM 生成假设性问题

**Phase 3（v1.3）：**
- 社区摘要（`community_summary` 类型）
- 跨文档 entity_card 去重

---

## 五、维度 4：关系图谱（Relations）

### 5.1 当前实现

**仅结构关系，规则生成：**

| 关系类型 | 生成方式 | 语义 |
|---------|---------|------|
| `previous` / `next` | 相邻 segment | 位置顺序 |
| `same_section` | 同 section 下两两配对 O(n²) | 同一主题 |
| `section_header_of` | heading → section 内容 | 标题归属 |
| `same_parent_section` | 同父 section | 兄弟关系 |

**关键问题：**
1. same_section O(n²) 爆炸（100 segment → 4950 条关系）
2. 纯位置关系，无语义判断——两个语义无关的段落只要在同一 section 就有 same_section 关系
3. 无语篇关系（阐述、条件、因果、对比等）
4. 关系建在 segments 上，但 retrieval_units 无法桥接到 segments（无 source_segment_id 外键）

### 5.2 工业最佳实践

#### 5.2.1 语篇关系（Discourse Relations / RST）

**来源：** Disco-RAG（萨尔大学/腾讯，2025-2026，3 benchmark SOTA）

**验证效果：** 移除语篇图谱，性能下降 4.97 分

**核心关系类型（Disco-RAG 验证集）：**

| 关系 | 含义 | 网络设备文档场景 |
|------|------|----------------|
| `ELABORATES` | B 详细阐述 A | 命令概述 → 详细参数说明 |
| `CONDITIONS` | B 是 A 的前提 | "需先激活 License" → "ADD NE 命令" |
| `RESULTS_IN` | A 导致 B | "执行 ADD NE" → "网元被添加" |
| `BACKGROUNDS` | B 为 A 提供背景 | 概念定义 → 命令说明 |
| `CONTRASTS_WITH` | A 和 B 对比 | "范围 1-100" vs "特定模式 1-50" |
| `SEQUENCES` | B 逻辑上跟随 A | 步骤 1 → 步骤 2 |
| `EVIDENCES` | B 佐证 A | 性能声明 → 测试数据表格 |
| `ENABLES` | B 使 A 成为可能 | "开启高级模式" → "MOD NE 高级参数" |

#### 5.2.2 语篇关系提取方法

**推荐：零样本 LLM 提取（Disco-RAG 验证）**

- Llama-3.3-70B 零样本达到 relation F1 = 58.6（接近微调模型 60.0）
- 8B 模型也能产生有用结构
- 滑动窗口：每次传入 10-20 个段落，非全量 O(n²)
- 基于结构关系预筛选候选对

**混合策略（推荐 v1.2）：**
1. 结构关系（v1.1 规则）→ 预筛选候选段落对
2. LLM 判断候选对的语篇关系类型
3. 写入同一张 `asset_raw_segment_relations`，用 relation_type 区分

#### 5.2.3 其他工业参考

| 系统 | 关系类型 | 说明 |
|------|---------|------|
| Microsoft GraphRAG | 实体级关系 | 实体 → 实体，无语篇关系 |
| LightRAG | 实体级关系 | 轻量级，1/100 成本 |
| Neo4j GraphRAG | Lexical Graph | 只有 NEXT_CHUNK/PREVIOUS_CHUNK |
| **Disco-RAG** | **段落级语篇关系** | **唯一做段落级语篇的，SOTA** |

### 5.3 差距分析

| 方面 | 当前 | 目标 |
|------|------|------|
| 关系类型 | 4 种结构关系 | 结构关系 + 8-12 种语篇关系 |
| 生成方式 | 纯规则 | 规则（结构）+ LLM（语篇） |
| same_section | O(n²) 无限制 | 距离上限 ≤ 5，或改为 section_header_of 替代 |
| 关系存储 | segment 级 | segment 级（正确，无需改） |
| retrieval_unit 桥接 | 无（source_refs JSON） | source_segment_id 外键直接 JOIN |

### 5.4 演进目标

**Phase 1（v1.2 立行）：**
- same_section 加距离上限（≤ 5）
- `asset_retrieval_units` 增加 `source_segment_id` 外键列
- Serving 层通过外键 JOIN 直接桥接 retrieval_unit → segment → relations

**Phase 2（v1.2 LLM 集成）：**
- 扩展 relation_type CHECK 约束，加入语篇关系标签
- 实现混合策略：结构关系预筛选 + LLM 语篇判断
- 利用 LLM Runtime 异步提交语篇关系提取任务

**Phase 3（v1.3）：**
- 实体级本体（entity → entity 三元组）
- 社区检测 + 摘要

---

## 六、维度 5：查询理解（Query Understanding）

### 6.1 当前实现

**Normalizer（`normalizer.py`）：**
- 意图检测：关键词匹配（"什么是" → concept, "怎么" → procedure）
- 关键词提取：`re.split(r"[\s,，、？?。.！!]+", query)` → stopword 过滤
- 别名映射：预定义中文→英文映射表（如 "添加" → "ADD"）
- **无中文分词**：连续中文无法拆分
- **无实体识别**：entities 从 request 传入，不做自动抽取

**QueryPlanner（`query_planner.py`）：**
- RulePlannerProvider：基于 intent 映射 retriever_config
- LLMPlannerProvider：slot 已预留但未实现

### 6.2 工业最佳实践

| 方法 | 来源 | 效果 | 复杂度 |
|------|------|------|--------|
| **同义词扩展** | 工业标准 | 最实用的第一步 | 低 |
| **HyDE** | ACL 2023 | 5-15% 检索提升 | 中 |
| **Multi-query** | LangChain | 覆盖多种表述 | 中 |
| **Step-back prompting** | Google DeepMind | 抽象到更广概念 | 中 |
| **Query decomposition** | 自适应 | 复杂问题拆子问题 | 高 |
| **LLM 实体抽取** | 工业标准 | 参数名/命令名识别 | 中 |

### 6.3 差距分析

| 方面 | 当前 | 目标 |
|------|------|------|
| 分词 | re.split（中文无效） | jieba 分词 |
| 意图检测 | 关键词匹配 | LLM 分类（4 类 intent） |
| 实体识别 | 无（依赖用户传入） | LLM NER（参数名/命令名/特性名） |
| 查询改写 | 无 | HyDE / Multi-query |
| 同义词 | 静态映射表 | LLM 动态扩展 + 领域词典 |
| 槽位填充 | 无 | LLM 提取 scope/product/scenario |

### 6.4 演进目标

**Phase 1（v1.2 立行）：**
- Normalizer 接入 jieba 分词
- FTS5 查询改为 OR 语义（不再双引号短语匹配）

**Phase 2（v1.2 LLM 集成）：**
- 实现 LLMNormalizer：意图分类 + 实体抽取 + 查询改写
- 利用 LLM Runtime 同步调用 `/execute` 端点
- HyDE：生成假设性答案，用其 embedding 检索（依赖向量通道）

**Phase 3（v1.3）：**
- Multi-query / Query decomposition

---

## 七、维度 6：检索通道（Retrieval Paths）

### 7.1 当前实现

**单路 FTS5 BM25：**
- `asset_retrieval_units_fts` 全文索引
- `tokenize = 'unicode61'`（不支持中文）
- JOIN 修复后（`fts.retrieval_unit_id`）可正常工作
- BM25 评分（负值，越负越相关）
- 无向量检索通道
- Graph 通道已实现（`graph_expander.py`）但因 source_refs contract 断裂无法生效

### 7.2 工业最佳实践

**标准三路检索架构（2025-2026 工业标准）：**

```
Query → [Query Transform]
  ├── BM25 (sparse, top-50)    ← FTS5 / Elasticsearch
  ├── Vector (dense, top-50)   ← FAISS / Qdrant / SQLite vec
  └── Graph (N-hop traversal)  ← 关系图 BFS
  → [RRF Fusion k=60]
```

| 通道 | 优势 | 劣势 | 模型 |
|------|------|------|------|
| BM25 (sparse) | 精确关键词匹配，无模型依赖 | 无法理解语义相似 | FTS5 内建 |
| Vector (dense) | 语义相似匹配，跨语言 | 需 embedding 模型 | BGE-M3 |
| Graph (traversal) | 结构/语篇关系扩展 | 依赖图谱质量 | 无模型 |

**重要发现（2026-03 arXiv）：** RRF 提升的召回率在 rerank + 截断后大部分被抵消。**简单单路 baseline + 强 reranker 可能就够了。**

### 7.3 差距分析

| 方面 | 当前 | 目标 |
|------|------|------|
| BM25 | 已实现（修复后可用） | 加入中文分词 |
| Vector | 无 | BGE-M3 + SQLite vec 或 FAISS |
| Graph | 已实现（contract 断裂） | 修复 contract，生效 |
| 多路融合 | IdentityFusion | RRF Fusion（已实现，待启用） |

### 7.4 演进目标

**Phase 1（v1.2 立行，让现有通道真正工作）：**
- 修复 source_refs contract（加 source_segment_id 外键）
- Graph 通道生效
- 中文分词接入

**Phase 2（v1.2 LLM 集成，增加向量通道）：**
- 新增 `asset_retrieval_embeddings` 表：`retrieval_unit_id, embedding BLOB, model_name`
- Mining 侧：build_retrieval_units 后，调用 LLM Runtime 生成 BGE-M3 embedding
- Serving 侧：新增 `VectorRetriever`，向量相似度检索
- 启用 RRF Fusion（k=60）融合 BM25 + Vector

**Phase 3（v1.3）：**
- 评估是否需要 Graph 作为独立检索通道（还是只作为扩展）
- 根据评估结果决定是否三路并行

---

## 八、维度 7：融合与重排（Fusion & Reranking）

### 8.1 当前实现

**Fusion（`fusion.py`）：**
- `IdentityFusion`：单路直接返回
- `RRFFusion`：已实现标准 RRF 公式 `1/(k+rank)`，k=60
- 待多路召回启用后生效

**Reranker（`reranker.py`）：**
- `ScoreReranker`：纯规则排序
- 角色偏好：`desired_roles` 指定的排在前面
- 块类型偏好：`desired_block_types` 指定的排在前面
- 硬截断：`plan.budget.max_items`
- **无相关性打分**：只做分类排序，不重新评估查询-文档相关性
- **无语义重排**：不理解查询意图和文档内容的语义关系

### 8.2 工业最佳实践

| 方法 | 来源 | 效果 | 复杂度 |
|------|------|------|--------|
| **Cross-Encoder Reranker** | 工业标准 | **+7.6pp，减少 35% 幻觉**（单次最大提升） | 中 |
| **MMR Diversity** | 工业标准 | 去除冗余结果 | 低 |
| **LLM Reranker** | 前沿 | 最高质量但成本高 | 高 |
| **规则偏好排序** | 当前实现 | 基础排序 | 低 |

**推荐 Reranker 模型：**
- 自部署中文：`BAAI/bge-reranker-v2-m3`（开源，多语言，680M 参数）
- API：`Cohere rerank-3.5`

**标准 Rerank Pipeline：**
```
BM25 top-50 + Vector top-50 → RRF Fusion top-30 → Cross-Encoder Rerank top-15 → MMR top-10
```

### 8.3 差距分析

| 方面 | 当前 | 目标 |
|------|------|------|
| 融合策略 | Identity（单路） | RRF（多路），已实现待启用 |
| 重排方式 | 规则偏好排序 | Cross-Encoder 语义重排 |
| 去重 | 无 | MMR 多样性 + unit_type 去重 |
| 低价值过滤 | 无 | heading/TOC/link 降权或过滤 |
| 精度 | 无法衡量 | RAGAS Faithfulness > 0.85 |

### 8.4 演进目标

**Phase 1（v1.2 立行）：**
- 启用 RRF Fusion（已实现）
- 结果去重：同一 document_snapshot_id + 相似文本 > 80% → 保留高分
- 低价值 block_type（heading、toc）降权

**Phase 2（v1.2 LLM 集成）：**
- 部署 bge-reranker-v2-m3 作为 Cross-Encoder Reranker
- 实现 `CrossEncoderReranker`：对 BM25 + Vector 融合后的 top-30 重新打分
- MMR 多样性：从 rerank 后结果中选 top-N，确保内容多样性

**Phase 3（v1.3）：**
- LLM Reranker（可选，成本高）
- Context Compression（压缩冗余上下文）

---

## 九、维度 8：图扩展（Graph Expansion）

### 9.1 当前实现

**GraphExpander（`graph_expander.py`）：**
- BFS 遍历 `asset_raw_segment_relations`，max_depth=2
- 支持关系类型过滤和 snapshot 约束
- **完全未生效**：`seed_segment_ids` 始终为空（source_refs contract 断裂）

**断裂链路：**
```
retrieval_unit → source_refs_json → parse_source_refs() → 期望 raw_segment_ids
                                                  → 实际得到 document_key + segment_index
                                                  → 返回 [] → seed_segment_ids = []
                                                  → graph_expander.expand([]) → 无扩展
```

### 9.2 工业最佳实践

**Disco-RAG 语篇扩展（SOTA）：**
1. 检索到 seed chunk 后，沿语篇关系边拉取支撑上下文
2. 优先沿 `ELABORATES`、`CONDITIONS`、`BACKGROUNDS` 边扩展
3. `CONTRASTS_WITH` 标记矛盾信息，避免 LLM 错误合并
4. `UNRELATED` 的段落即使在同一 section 也降权

**Neo4j Graph-Guided Retrieval（Type 2）：**
- seed → 1-hop neighbors → 按关系权重排序 → top-K 加入 context
- 支持多种遍历策略：BFS、DFS、weighted

### 9.3 差距分析

| 方面 | 当前 | 目标 |
|------|------|------|
| 扩展触发 | source_refs 解析失败 → 不触发 | source_segment_id 外键 → 直接触发 |
| 关系类型 | 结构关系（prev/next/same_section） | + 语篇关系（ELABORATES 等） |
| 扩展策略 | BFS（无差别） | 语篇引导（按关系类型优先级扩展） |
| 冲突处理 | 无 | CONTRASTS_WITH 标记矛盾 |
| snapshot 约束 | 已实现（但不生效） | 生效 |

### 9.4 演进目标

**Phase 1（v1.2 立行，修复断裂）：**
- `asset_retrieval_units` 增加 `source_segment_id` 外键
- Assembler 直接通过外键 JOIN 获取 segment ID
- Graph 通道生效

**Phase 2（v1.2 LLM 集成）：**
- 语篇引导扩展：按关系类型优先级（ELABORATES > CONDITIONS > BACKGROUNDS > 其他）
- 冲突检测：CONTRASTS_WITH 关系标记矛盾，Assembler 中加入冲突提示
- 扩展结果角色标记：seed（主召回）、expanded（语篇扩展）、context（结构扩展）

---

## 十、维度 9：评估体系（Evaluation）

### 10.1 当前实现

**无评估体系。** 靠人工测试验证。

### 10.2 工业最佳实践

**RAGAS 框架（Retrieval Augmented Generation Assessment）：**

| 指标 | 含义 | 目标值 |
|------|------|--------|
| Faithfulness | 生成答案是否忠实于检索上下文 | > 0.85 |
| Context Precision | 检索结果中相关内容的比例 | > 0.75 |
| Context Recall | 相关内容被检索到的比例 | > 0.80 |
| Answer Relevancy | 答案与查询的相关性 | > 0.80 |

**Golden Set 构建：**
- 50-200 个标注好的 (query, expected_results) 对
- 覆盖所有意图类型：command、concept、procedure、troubleshooting
- 覆盖中英文混合查询
- 每个版本回归测试

### 10.3 演进目标

**Phase 1（v1.2）：**
- 构建 50 个 golden set 查询
- 实现 `eval/` 目录：评估脚本 + golden set 数据
- 自动化：每次 Mining build 后跑评估，输出 Context Precision / Recall

**Phase 2（v1.3）：**
- RAGAS 完整评估（需要 LLM 生成答案）
- 持续集成：CI 中跑评估，低于阈值则告警

---

## 十一、source_refs Contract 修复（横切关注点）

**这是当前系统最大的阻塞问题。** 它同时影响维度 3（检索单元）、维度 4（关系图谱）、维度 8（图扩展）。

### 11.1 问题

**Mining 写入：**
```python
source_refs_json = {"document_key": "doc:/lte/config.md", "segment_index": 5, "offsets": {...}}
```

**Serving 期望：**
```python
seg_ids = parse_source_refs(source_refs_json)  # 期望 {"raw_segment_ids": ["uuid1", "uuid2"]}
# 实际返回 [] → 整条链路断裂
```

### 11.2 根因

1. `build_retrieval_units()` 在 `build_relations()` 之前执行（pipeline 顺序）
2. 即使反过来，retrieval_units 生成时也拿不到 segment UUID（UUID 在 relations 中生成）
3. JSON 格式完全不同，Serving 无法解析

### 11.3 推荐方案

**方案：增加 `source_segment_id` 外键列**

```sql
ALTER TABLE asset_retrieval_units
ADD COLUMN source_segment_id TEXT REFERENCES asset_raw_segments(id);
```

**Mining 侧改动（pipeline 顺序调整）：**
```
当前：parse → segment → enrich → build_relations → build_retrieval_units
目标：parse → segment → enrich → build_relations → build_retrieval_units
                                                        ↑ relations 产出的 seg_ids map 直接传入
```

`build_retrieval_units()` 接收 `seg_ids: dict[str, str]` 参数：
```python
def build_retrieval_units(
    segments: list[RawSegmentData],
    *,
    seg_ids: dict[str, str] | None = None,  # 新增：segment_key → UUID
    document_key: str = "",
    question_generator: QuestionGenerator | None = None,
) -> list[RetrievalUnitData]:
```

每个 unit 的 `source_segment_id` 直接填入 segment UUID。

**Serving 侧改动（Assembler）：**
```python
# 当前：解析 source_refs_json → 失败
# 目标：直接用 source_segment_id
def _resolve_candidate_sources(self, candidate: RetrievalCandidate) -> list[str]:
    seg_id = candidate.metadata.get("source_segment_id")
    if seg_id:
        return [seg_id]
    # fallback: 解析 source_refs_json
    ...
```

---

## 十二、实施路线图

### Phase 1：修复阻塞问题（1-2 天）

| 优先级 | 任务 | 负责 | 预期效果 |
|--------|------|------|---------|
| **P0** | source_refs contract 修复（加 source_segment_id 外键） | Mining | 图扩展链路打通 |
| **P0** | 中文分词：Mining 端 search_text jieba 预分词 | Mining | 中文查询可匹配 |
| **P0** | FTS5 查询策略：双引号短语 → OR 语义 | Serving | 查询召回率提升 |
| **P0** | Normalizer jieba 分词 | Serving | 中文关键词正确提取 |

### Phase 2：质量提升（1-2 周）

| 优先级 | 任务 | 负责 | 预期效果 |
|--------|------|------|---------|
| **P1** | 结果去重（raw_text + contextual_text 重叠） | Mining | 消除冗余结果 |
| **P1** | low-value block_type 降权（heading/toc） | Serving | 高价值结果优先 |
| **P1** | same_section O(n²) 加距离上限 | Mining | 大文档性能 |
| **P1** | Golden set 构建（50 条） | 联合 | 可量化评估 |
| **P1** | entity_card 内容改进 | Mining | 实体检索更有效 |

### Phase 3：LLM 集成（2-4 周）

| 优先级 | 任务 | 负责 | 预期效果 |
|--------|------|------|---------|
| **P1** | 语篇关系提取（零样本 LLM + 结构预筛选） | Mining | 语义关系图谱 |
| **P1** | Anthropic contextual retrieval（LLM 上下文描述） | Mining | 检索失败率降低 49% |
| **P1** | LLM 查询理解（意图 + 实体 + 查询改写） | Serving | 查询意图精准 |
| **P2** | 向量检索通道（BGE-M3 embedding） | 联合 | 语义相似匹配 |
| **P2** | Cross-Encoder Reranker（bge-reranker-v2-m3） | Serving | +7.6pp 精度 |
| **P2** | 父子层级分块（parent_context 类型） | Mining | +15.3% hit rate |
| **P2** | HyDE 查询改写 | Serving | 5-15% 检索提升 |

### Phase 4：高级能力（v1.3）

| 优先级 | 任务 | 负责 | 预期效果 |
|--------|------|------|---------|
| **P3** | 社区摘要（Microsoft GraphRAG 模式） | Mining | 全局问题回答能力 |
| **P3** | 实体级本体（entity → entity 三元组） | Mining | 知识推理能力 |
| **P3** | 语义分块（纯文本文档） | Mining | 无结构文档支持 |
| **P3** | RAGAS 完整评估 | 联合 | 质量可量化 |
| **P3** | LLM Reranker（可选） | Serving | 最高精度 |

---

## 十三、Mining vs Serving 职责矩阵

| 能力 | Mining | Serving |
|------|--------|---------|
| **文本分块** | 实现（结构 + 语义） | 消费 |
| **中文分词** | 实现（search_text 预分词） | 消费（FTS5 查询适配） |
| **检索单元构建** | 实现（所有类型） | 消费 |
| **Embedding 生成** | 实现（调用 LLM Runtime） | 消费（向量检索） |
| **关系图谱构建** | 实现（结构 + 语篇） | 消费（图遍历扩展） |
| **source_refs** | 实现（外键 + JSON） | 消费（桥接到 segments） |
| **查询理解** | - | 实现（normalizer + LLM） |
| **检索执行** | - | 实现（BM25 + Vector + Graph） |
| **融合** | - | 实现（RRF） |
| **重排** | - | 实现（规则 + CrossEncoder） |
| **上下文组装** | - | 实现（Assembler） |
| **评估数据** | 提供（golden set 标注） | 执行（评估脚本） |

---

## 十四、参考资料

### 核心论文

| 论文 | 关键贡献 |
|------|---------|
| [Disco-RAG](https://arxiv.org/html/2601.04377v5) | 首个 RST 语篇关系 RAG 框架，3 benchmark SOTA |
| [HyDE (ACL 2023)](https://arxiv.org/abs/2212.10496) | 假设文档嵌入，5-15% 检索提升 |
| [Anthropic Contextual Retrieval](https://www.anthropic.com/research/building-effective-agents) | 上下文增强，49% 失败率降低 |
| [Microsoft GraphRAG](https://microsoft.github.io/graphrag/) | 社区摘要 + 全局检索 |
| [LightRAG (ACL 2025)](https://aclanthology.org/2025.findings-emnlp.568/) | 轻量实体级 KG |
| [Semantic Chunking](https://arxiv.org/abs/2405.11118) | 基于语义断点的分块方法 |
| [Late Chunking (Jina AI)](https://jina.ai/news/late-chunking-in-long-context-embedding-models/) | 先 embedding 后分块 |

### 模型推荐

| 用途 | 模型 | 部署方式 |
|------|------|---------|
| 中文分词 | jieba | Python 库 |
| Embedding | BAAI/bge-m3 | LLM Runtime / 自部署 |
| Reranker | BAAI/bge-reranker-v2-m3 | 自部署 |
| NER | chinese-roberta-wwm-ext + BiLSTM + CRF | 自部署 |
| 语篇关系提取 | LLM 零样本（DeepSeek / Qwen） | LLM Runtime |

### 评估框架

| 框架 | 指标 |
|------|------|
| RAGAS | Faithfulness, Context Precision, Context Recall, Answer Relevancy |
| Golden Set | 自建 50-200 条 |

---

## 十五、附录：关键代码路径

### A.1 Mining Pipeline 顺序（当前 vs 目标）

```
当前：parse → segment → enrich → build_relations → build_retrieval_units → select_snapshot → assemble_build → validate_build → publish_release

目标（v1.2）：parse → segment → enrich → build_relations → build_retrieval_units → build_embeddings → build_discourse_relations → select_snapshot → assemble_build → validate_build → publish_release
                                                                    ↑ 新增                    ↑ 新增
```

### A.2 Serving Pipeline（当前 vs 目标）

```
当前：
SearchRequest → Normalizer(规则) → QueryPlanner(规则) → ActiveScope
  → RetrieverManager(BM25 单路) → IdentityFusion → ScoreReranker(规则偏好)
  → Assembler(contract 断裂) → ContextPack

目标（v1.2）：
SearchRequest → Normalizer(jieba + LLM) → QueryPlanner(LLM + HyDE) → ActiveScope
  → RetrieverManager(BM25 + Vector + Graph 三路) → RRFFusion(k=60)
  → CrossEncoderReranker(bge-reranker-v2-m3) → Assembler(语篇扩展 + 冲突检测)
  → ContextPack
```

### A.3 数据模型变更

```sql
-- Phase 1: source_segment_id 外键
ALTER TABLE asset_retrieval_units
ADD COLUMN source_segment_id TEXT REFERENCES asset_raw_segments(id);

-- Phase 2: embedding 表
CREATE TABLE IF NOT EXISTS asset_retrieval_embeddings (
    id TEXT PRIMARY KEY,
    retrieval_unit_id TEXT NOT NULL REFERENCES asset_retrieval_units(id),
    embedding BLOB NOT NULL,
    model_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Phase 2: parent_unit_id 父子层级
ALTER TABLE asset_retrieval_units
ADD COLUMN parent_unit_id TEXT REFERENCES asset_retrieval_units(id);

-- Phase 2: 扩展 relation_type CHECK 约束
-- 加入：ELABORATES, CONDITIONS, RESULTS_IN, BACKGROUNDS, CONTRASTS_WITH,
--       SEQUENCES, EVIDENCES, ENABLES, SUMMARIZES, JUSTIFIES, PARALLELS, UNRELATED
```
