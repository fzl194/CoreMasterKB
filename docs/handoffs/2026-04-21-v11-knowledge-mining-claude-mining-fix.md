# v1.1 Knowledge Mining — Codex Review Fix

- **Task**: TASK-20260421-v11-knowledge-mining
- **Date**: 2026-04-21
- **From**: Claude Mining
- **Based on**: `docs/analysis/2026-04-21-v11-knowledge-mining-codex-review.md`

## Codex 审查概要

Codex 提出 4 个 P1 + 2 个 P2，核心判断：当前实现是"可运行的 rule-based pipeline"，还不是"可快速接入统一 LLM Runtime 的可演进底座"。

## 修复清单

### P1. enrich 没有成为正式可替换理解阶段

**问题**: 实体抽取和角色分类写死在 segmentation，enrich 只做修饰。

**修复**:
- `segmentation` 只做结构切分，产出 `semantic_role="unknown"` 和空 `entity_refs_json=[]`
- `enrich` 成为正式理解阶段：接受 `EntityExtractor` + `RoleClassifier` Protocol 接口
- `enrich_segments()` 新签名接受 `entity_extractor=` 和 `role_classifier=` 参数
- v1.1 提供 `RuleBasedEnricher`，v1.2 可注入 LLM 实现，不影响 segmentation 和 retrieval_units

**改动文件**:
- `segmentation/__init__.py` — 移除 extractor/classifier 依赖，segment_document 不再接受理解参数
- `enrich/__init__.py` — 完整重写，承担 entity extraction + role classification + metadata enrichment
- `jobs/run.py` — extractor/classifier 传给 enrich 而非 segmentation

### P1. retrieval_units 缺 generated_question

**问题**: plan 承诺 raw_text + contextual_text + generated_question，实现改成了 entity_card，没有 LLM 接入口。

**修复**:
- 新增 `QuestionGenerator` Protocol 接口
- v1.1 默认 `NoOpQuestionGenerator`（返回空列表，LLM Runtime 未接入）
- `generated_question` unit 类型正式落库，写入 `llm_result_refs_json`
- v1.2 只需实现 `LlmQuestionGenerator` 注入即可
- `entity_card` 保留

**改动文件**: `retrieval_units/__init__.py`

### P1. build/release 固定 full 模式

**问题**: 每个文档一律 action="NEW"，build_mode 固定 "full"，没有变更集语义。

**修复**:
- 新增 `classify_documents()` — 对比 prev active build 的 snapshot，产出 NEW/UPDATE/SKIP/REMOVE
- `assemble_build()` 自动选择 full vs incremental
- document 注册时根据已有 document hash 动态判定 action
- incremental merge 语义激活：未变更的父 build snapshot 自动 retain

**改动文件**: `publishing/__init__.py`, `jobs/run.py`

### P1. run 失败语义不正确

**问题**: 全局异常不 fail_run，局部失败仍发布 active release。

**修复**:
- `run()` 外层异常调用 `tracker.fail_run()`
- 局部失败时默认阻断 active release 发布（`publish_on_partial_failure=False`）
- run status 三级：`completed` / `completed_with_errors` / `completed_partial`
- `run_id` 在 `run()` 中预生成，确保异常时仍能标记

**改动文件**: `jobs/run.py`

### P2. 旧 v0.5 测试残留

**修复**: 13 个旧测试文件移到 `old/knowledge_mining_m1/tests/`，`knowledge_mining/tests/` 只保留 v1.1 测试。

### P2. DB adapter 缺父目录创建

**修复**: `_DB.open()` 增加 `Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)`。

## 验证

30 tests passed，端到端 pipeline 验证通过。

## LLM Runtime 对齐

本次修复为 v1.2 LLM 集成建立了三个正式接缝：

1. **enrich 阶段**: `EntityExtractor` + `RoleClassifier` Protocol → v1.2 实现 `LlmEntityExtractor` + `LlmRoleClassifier`
2. **retrieval_units 阶段**: `QuestionGenerator` Protocol → v1.2 实现 `LlmQuestionGenerator`
3. **generated_question 落库**: `llm_result_refs_json` 字段预留，v1.2 写入 LLM 调用审计引用

接入方式：jobs/run.py 只需替换构造参数，不改主链。
