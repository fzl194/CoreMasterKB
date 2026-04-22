# CoreMasterKB v1.2 Mining Retrieval View 设计文档

- 日期：2026-04-22
- 作者：Claude Mining
- 状态：已批准
- 前置：Codex `docs/analysis/2026-04-22-v12-retrieval-view-architecture-codex-review.md`
- 范围：`knowledge_mining` 模块 v1.2 演进

## 1. 目标

正式建立 Retrieval View Layer，从"跑通"进入"可用"。

核心收口：
- `raw_segment` 作为 truth layer
- `retrieval_unit` 作为 retrieval view layer
- `source_segment_id` 作为一等桥接
- FTS5 中文可用（jieba 预分词）
- LLM 通过统一 runtime contract 接入 generated_question 和 enrich

## 2. 实施范围

### P1 必做（4 项）

| # | 事项 | 核心改动 |
|---|------|---------|
| P1-1 | `source_segment_id` 强桥接 | schema 加列 + models.py + retrieval_units + pipeline |
| P1-2 | jieba 预分词写入 `search_text` | retrieval_units 中 jieba.cut + text_utils CJK token 估算 |
| P1-3 | `generated_question` 接入真实 LLM | 新建 llm_client.py + LlmQuestionGenerator + 模板预注册 |
| P1-4 | `QuestionGenerator` 与 llm_service 对齐 | caller_domain="mining", pipeline_stage="retrieval_units" |

### P2 加固（5 项）

| # | 事项 | 核心改动 |
|---|------|---------|
| P2-1 | same_section 加距离上限 | relations 加 max_distance=5 |
| P2-2 | validate_build 真实校验 | publishing 检查至少 1 个 active snapshot |
| P2-3 | entity_card 内容丰富化 | 从 enrich 结果提取更多实体描述文本 |
| P2-4 | UPDATE 场景清理旧数据 | 写入前清理旧 snapshot 下的 segments/relations/units |
| P2-5 | enrich batch-capable 接口 | Protocol 新增 enrich_batch() 方法 |

## 3. Schema 变更

直接修改 `databases/asset_core/schemas/001_asset_core.sqlite.sql`：

```sql
-- asset_retrieval_units 新增列
source_segment_id TEXT REFERENCES asset_raw_segments(id) ON DELETE SET NULL

-- 新增索引
CREATE INDEX IF NOT EXISTS idx_asset_retrieval_units_source_segment
    ON asset_retrieval_units(source_segment_id);
```

## 4. LLM 集成设计

### 4.1 客户端位置

`knowledge_mining/mining/llm_client.py` — 独立 HTTP 客户端，不 import llm_service 包。

### 4.2 调用模式

| 用途 | 模式 | 端点 |
|------|------|------|
| generated_question | submit + poll（批量异步） | POST /api/v1/tasks + GET /api/v1/tasks/{id}/result |
| enrich（未来） | submit + poll | 同上 |
| 未来 query understanding | execute（同步） | POST /api/v1/execute |

### 4.3 模板预注册

```python
# mining/llm_templates.py
TEMPLATES = [
    {
        "template_key": "mining-question-gen",
        "template_version": "1",
        "purpose": "从段落内容生成假设性检索问题",
        "system_prompt": "你是通信网络知识库的检索优化助手。",
        "user_prompt_template": "根据以下技术文档段落，生成 2-3 个用户可能提出的问题。\n\n段落标题：$title\n段落内容：$content\n\n输出 JSON 数组，每个元素包含 question 字段。",
        "expected_output_type": "json_array",
    },
]
```

### 4.4 失败策略

- LLM 失败不阻塞 pipeline
- `LlmQuestionGenerator` 内部 try/except，失败时返回空列表
- `llm_result_refs_json` 记录 `{"task_id": "...", "status": "succeeded/failed"}`

### 4.5 jieba 容错

```python
try:
    import jieba
    search_text = " ".join(jieba.cut(raw_text))
except ImportError:
    search_text = raw_text  # 回退原文
```

## 5. Pipeline 变更

### 5.1 build_retrieval_units 签名变更

```python
def build_retrieval_units(
    segments: list[RawSegmentData],
    *,
    seg_ids: dict[str, str] | None = None,  # 新增：segment_key → UUID
    document_key: str = "",
    question_generator: QuestionGenerator | None = None,
) -> list[RetrievalUnitData]:
```

### 5.2 jobs/run.py 调用链

```
当前：build_relations(segments) → relations, seg_id_map
      build_retrieval_units(segments, document_key=doc_key)
                                              ↑ 拿不到 seg_ids

目标：build_relations(segments) → relations, seg_id_map
      build_retrieval_units(segments, seg_ids=seg_id_map, document_key=doc_key,
                            question_generator=llm_qg)
                                              ↑ 直接传入 seg_ids + LLM generator
```

### 5.3 enrich batch 接口

```python
class Enricher(Protocol):
    def enrich(self, segment: RawSegmentData, **kwargs) -> RawSegmentData: ...
    def enrich_batch(self, segments: list[RawSegmentData], **kwargs) -> list[RawSegmentData]:
        # 默认实现：逐个调用 enrich
        return [self.enrich(seg, **kwargs) for seg in segments]
```

## 6. 数据库写入变更

### 6.1 db.py

- `insert_retrieval_unit()` 增加 `source_segment_id` 参数
- 新增 `delete_segments_by_snapshot(snapshot_id)` 方法（UPDATE 清理用）
- 新增 `delete_relations_by_snapshot(snapshot_id)` 方法
- 新增 `delete_retrieval_units_by_snapshot(snapshot_id)` 方法

### 6.2 UPDATE 场景清理

在 `jobs/run.py` 的非 SKIP 分支，写入新数据前：

```python
if action == "UPDATE":
    asset_db.delete_retrieval_units_by_snapshot(snapshot_id)
    asset_db.delete_relations_by_snapshot(snapshot_id)
    asset_db.delete_segments_by_snapshot(snapshot_id)
    asset_db.commit()
```

## 7. P2 详细设计

### 7.1 same_section 距离上限

```python
# relations/__init__.py
for i in range(len(section_segs)):
    for j in range(i + 1, min(i + max_distance + 1, len(section_segs))):
        if abs(section_segs[i].segment_index - section_segs[j].segment_index) <= max_distance:
            emit_relation("same_section", ...)
```

### 7.2 validate_build 真实校验

```python
# publishing/__init__.py
def validate_build(asset_db, build_id):
    snapshots = asset_db.get_build_document_snapshots(build_id)
    if not snapshots:
        raise ValueError(f"Build {build_id} has no active snapshots")
    for snap in snapshots:
        if snap["selection_status"] != "active":
            continue
        # 检查 snapshot 有 segments
        segs = asset_db.count_segments_by_snapshot(snap["document_snapshot_id"])
        if segs == 0:
            raise ValueError(f"Snapshot {snap['document_snapshot_id']} has no segments")
```

### 7.3 entity_card 丰富化

```python
# 当前：f"{name} ({etype}) — 见 {section_title}"
# 目标：提取实体周边上下文
description = _extract_entity_context(name, segment.raw_text, window=80)
card_text = f"{name}（{etype}）{description}"
```

## 8. 不做的事情

- 不加 `parent_unit_id`（v1.3）
- 不加语篇关系（v1.3）
- 不加 embedding 计算（v1.3）
- 不改 Serving 代码
- 不改 llm_service 代码

## 9. 验收标准

| 能力 | 验收方式 |
|------|---------|
| source_segment_id | 每个 retrieval_unit 都有非空 source_segment_id |
| jieba 分词 | search_text 为空格分词结果，FTS5 中文查询命中 |
| generated_question | 部分 segment 有 generated_question unit，llm_result_refs_json 有 task_id |
| same_section | 100 segment section 关系数从 ~4950 降到 < 500 |
| validate_build | 空 build 无法通过验证 |
| UPDATE 清理 | 重跑 pipeline 无旧数据残留 |
| enrich batch | Protocol 有 enrich_batch 方法，默认逐个调用 |
| entity_card | card 文本包含实体描述上下文 |
| 回归测试 | 30 测试全部通过 |

## 10. 参考文档

- Codex v1.2 架构：`docs/analysis/2026-04-22-v12-retrieval-view-architecture-codex-review.md`
- 演进指导书：`.dev/2026-04-22-coremasterkb-retrieval-evolution-guide.md`
- 演进待办：`.dev/2026-04-22-v12-evolution-backlog.md`
- LLM Service handoff：`docs/handoffs/2026-04-21-v11-llm-service-claude-llm-handoff.md`
