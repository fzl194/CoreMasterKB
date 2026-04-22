# Serving Retrieval 演进研究笔记

> 日期：2026-04-22
> 状态：研究阶段，待与 Mining 统一收口

## 工业级检索现状研究 (2025-2026)

### Graph-RAG 四类（Neo4j 分类）
- Type 1: Graph-Enhanced Vector Search（向量 + 图元数据过滤）
- Type 2: Graph-Guided Retrieval（图遍历引导检索）← 当前 CoreMasterKB 的目标
- Type 3: Graph-Based Summarization（Microsoft GraphRAG，LLM 实体抽取 + Leiden 社区）
- Type 4: Temporal Knowledge Graph（Agent 记忆）

### Microsoft GraphRAG 关键模式
- 实体/关系抽取 → Leiden 社区检测 → 分层摘要
- Local Search: 实体邻域 + 关联文本
- Global Search: 社区摘要聚合
- DRIFT Search: Primer → Follow-up → Output Hierarchy，减少 40-60% 成本
- Dynamic Community Selection: 减少 79% token 用量

### 标准 RAG Pipeline（2026 工业标准）
```
Query → [Query Transform] → [Parallel Retrieval]
  ├── BM25 (sparse, top-50)
  ├── Vector (dense, top-50)
  └── Graph (N-hop traversal)
  → [RRF Fusion k=60] → [Cross-Encoder Rerank top-15] → [MMR Diversity] → LLM
```

### RRF 注意事项
- k=60 是标准默认值
- 但 2026-03 arXiv 论文指出：RRF 提升的召回率在 rerank + 截断后大部分被抵消
- 简单单路 baseline + 强 reranker 可能就够了

### Reranker 推荐
- 自部署中文：BAAI/bge-reranker-v2-m3（开源，多语言）
- API：Cohere rerank-3.5
- Cross-Encoder 是单次最大提升环节：+7.6pp，减少 35% 幻觉

### 中文检索关键
- jieba 预分词 + FTS5 unicode61 是最简单方案
- FTS5 应索引 search_text（预分词）而非 text（原文）
- NER：chinese-roberta-wwm-ext + BiLSTM + CRF

### 评估框架
- RAGAS：Faithfulness > 0.85, Context Precision > 0.75, Context Recall > 0.80
- 先建 50-200 golden set

## v1.1 当前问题

1. FTS5 JOIN bug（已修复：rowid → retrieval_unit_id）
2. source_refs 格式不对齐：Mining 输出 {document_key, segment_index, offsets}，Serving 期望 {raw_segment_ids}
3. 整条下钻链路断裂：无 source segments → 无 graph expansion → 无 relations → 无 sources
4. 短语查询太严格：双引号包裹导致 OR 语义丢失
5. 无中文分词："什么是业务感知" 被当做一个 token
6. 结果重复：raw_text + contextual_text 两种 unit_type 内容重叠
7. 低价值结果：heading/TOC/link 排名过高

## 待研究

- [ ] Mining 的 retrieval unit 构建逻辑
- [ ] Mining 的 source_refs 写入格式
- [ ] 统一框架：检索单元构建（Mining） + 检索执行（Serving）
