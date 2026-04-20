# M1 Agent Serving v0.5 Fix Codex Review

## 审查背景

本轮审查对象是 Claude Serving 针对上一轮 Codex review 的修复链，重点提交为：

```text
3978865 [claude-serving]: fix Codex review P1-P3 — tolerant reader + contract tests
1c55552 [claude-serving]: self-review fixes — externalize config + immutability + SQL hardening
e818044 [claude-serving]: send Codex review fix completion message
```

审查依据：

- `docs/architecture/2026-04-15-mining-serving-parallel-design.md`
- `docs/messages/TASK-20260415-m1-agent-serving.md`
- `docs/analysis/2026-04-17-m1-agent-serving-v05-codex-review.md`
- `knowledge_assets/schemas/001_asset_core.sqlite.sql`
- `agent_serving/serving/**`
- `agent_serving/tests/**`
- `data/m1_contract_corpus/m1_contract_asset.sqlite`
- `data/m1_realistic_corpus/m1_realistic_asset.sqlite`

总体结论：Serving 已经从 command lookup 继续向 generic evidence retrieval 收敛，QueryPlan/EvidencePack 主线保留正确；DB 路径配置、真实 Mining SQLite fixture 读取、结构化 evidence 返回、active version 检测、JSON 容错读取等上一轮 P1/P2 大多已有实现。但当前仍不能直接闭环验收，主要问题集中在真实问题下的召回质量、scope 契约覆盖和来源信息完整性。

## 审查范围

本次审查覆盖：

- FastAPI `/search` 与 `/command-usage` 管线
- `QueryNormalizer` / `QueryPlan`
- `AssetRepository` 的 active version、canonical search、drilldown、scope/entity JSON 容错
- `EvidenceAssembler` 的 evidence / variants / conflicts / gaps 组装
- 真实 Mining DB contract tests
- 运行测试结果

未覆盖：

- 生产部署配置
- 未来 embedding / rerank / ontology / LLM planner
- Mining 侧当前未完成的 semantic/entity 抽取质量

## 发现的问题

### P1: 真实 Mining DB 上的关键词召回过宽，EvidencePack 容易返回明显不相关证据

位置：

- `agent_serving/serving/repositories/asset_repo.py:80`
- `agent_serving/serving/repositories/asset_repo.py:86`
- `agent_serving/serving/repositories/asset_repo.py:93`

当前 `search_canonical()` 对关键词使用：

```text
keyword1 OR keyword2 OR keyword3 ...
LIMIT 10
```

没有停用词过滤、没有命中词数量统计、没有相关性排序，也没有先取候选再评分。真实 Mining DB 上定向验证时，问题：

```text
free5GC 的 registerIPv4 和 bindingIPv4 有什么区别？
```

返回的前几条 evidence 包括网络切片、N4 排障、NRF 定义等，与问题核心对象不匹配。原因是 query 被切成 `free5GC / 的 / registerIPv4 / 和 / bindingIPv4 / 有什么区别`，其中 `的`、`和` 这类高频词参与 OR 召回，`LIMIT` 又在评分前执行，导致不相关 canonical 抢占结果。

这会直接影响 M1 的核心目标：Serving 返回的是 Agent 可用 evidence pack，而不是随便命中的文本。

建议修复：

- Normalizer 增加中英文停用词过滤，去掉 `的/和/与/什么/怎么/有哪些/区别/问题` 等泛词。
- 对关键词长度和信息量设阈值，至少保留 `registerIPv4/bindingIPv4/free5GC` 这类有效词。
- SQL 可以先召回较大候选集，例如 50，再在 Python 侧打分后截断。
- 打分至少考虑：有效关键词命中数、实体命中、scope 命中、semantic_role/block_type 偏好、quality_score、variant penalty。
- 测试不能只断言 `len(results) >= 1`，需要断言 top evidence 命中关键对象。

### P2: QueryScope 未覆盖 scenarios/authors，显式 request scope 会被静默丢弃

位置：

- `agent_serving/serving/schemas/models.py:36`
- `agent_serving/serving/repositories/asset_repo.py:289`
- `agent_serving/serving/application/assembler.py:385`

架构文档要求 scope_json 至少兼容：

```text
products/product_versions/network_elements/projects/domains/scenarios/authors
```

当前 `QueryScope` 只有：

```text
products/product_versions/network_elements/projects/domains
```

实测：

```python
SearchRequest(query="q", scope={"scenarios": ["coldstart"]})
```

会被 Pydantic 解析成空 scope，`scenarios` 被静默忽略。`authors` 同理。

影响：

- 专家文档、项目经验文档、场景化文档无法通过显式 scope 过滤。
- 这与我们“未来语料不一定是产品文档”的架构目标不一致。

建议修复：

- `QueryScope` 增加 `scenarios`、`authors`。
- `_parse_scope()`、`_matches_scope()`、`_collect_scope()`、`_build_normalized_str()` 同步支持。
- 测试覆盖 plural/singular：`scenario/scenarios`、`author/authors`。
- 显式 request 中出现未知 scope 字段时，不建议静默丢弃；至少 debug 模式下返回 ignored fields。

### P2: scope_variant 的“scope sufficient”判断过窄，只看 products

位置：

- `agent_serving/serving/repositories/asset_repo.py:275`

当前逻辑：

```python
return bool(scope.products)
```

这意味着只有指定 product 才被认为 scope 足够。实际 M1 的 scope_variant 是通用 scope 维度差异，不限产品。用户可能只指定：

```text
project
domain
scenario
author
product_version
network_element
```

这些约束也可能足以选择某个 variant。当前实现会把这些场景下本可匹配的 `scope_variant` 放进 variants/gaps，而不是 evidence。

建议修复：

- 根据 `canonical_segment_sources.metadata_json.variant_dimensions` 或 source/doc scope 中实际差异维度判断是否足够。
- M1 简化版可先定义：只要用户提供的约束覆盖了 variant rows 的差异维度，就视为 sufficient。
- 不要把 product 作为 scope_variant 的唯一主轴。

### P2: scope 过滤遇到文档缺少被约束维度时直接放行，容易把未知 scope 当匹配

位置：

- `agent_serving/serving/repositories/asset_repo.py:305`

当前 `_matches_scope()` 对每个被约束维度，如果文档 scope_json 没有对应字段，会 `continue`，最终返回 True。这种策略对基础召回是容错的，但对 evidence/variant 选择过于宽松。

示例：

```text
请求 scope.products = ["UDG"]
某 evidence 的 doc_scope_json 没有 products/product 字段
当前结果：匹配
```

这会让 scope 未知的 raw evidence 进入普通 evidence，削弱“scope_variant 不应混入普通 evidence”的约束。

建议修复：

- 区分“召回容错”和“evidence scope 选择”：
  - canonical 召回阶段：scope 缺失可保留候选但降权。
  - drilldown evidence 阶段：用户显式约束的维度缺失时，不应直接视为匹配；可以放入 variants/gaps 或 unknown_scope。
- 至少对 `scope_variant` 不应把缺失差异维度当作匹配。

### P2: SourceRef / UnparsedDocument 仍未返回 processing_profile_json

位置：

- `agent_serving/serving/schemas/models.py:111`
- `agent_serving/serving/schemas/models.py:140`
- `agent_serving/serving/application/assembler.py:130`
- `agent_serving/serving/application/assembler.py:287`
- `agent_serving/serving/repositories/asset_repo.py:52`

上一轮要求下钻时读取并返回：

```text
raw_documents.file_type/document_type/tags_json/processing_profile_json
```

当前 repo 的 drilldown SQL 已经 select 了 `rd.processing_profile_json`，但 `SourceRef` 没有字段承载，assembler 也没有输出。`get_unparsed_documents()` 只 select 到 `tags_json`，没有 select `processing_profile_json`；`UnparsedDocument` 也没有 `tags/processing_profile` 字段。

影响：

- Agent 无法解释 HTML/PDF/DOCX 为什么只登记不切片。
- source_audit 类问题不能给出 parser/parse_status/skip_reason。

建议修复：

- `SourceRef` 增加 `processing_profile: dict`。
- `UnparsedDocument` 增加 `tags: list[str]`、`processing_profile: dict`。
- repo 的 `get_unparsed_documents()` select `processing_profile_json`。
- assembler 解析并返回。
- 测试断言 unparsed docs 包含 `parse_status=skipped` 或等价信息。

### P2: 真实 Mining DB contract tests 断言偏弱，不能证明问题级闭环

位置：

- `agent_serving/tests/test_mining_contract.py`

新增 contract tests 能证明 Serving 可以打开两个 Mining SQLite DB、读取 active version、做基础 search/drilldown，这是明显进步。但大多数断言仍停留在：

```text
len(results) >= 1
json.loads(...) is dict
file_type is not None
```

没有断言：

- 对应 questions.yaml 的问题能召回正确 evidence。
- top evidence 包含关键对象。
- source_audit 问题能返回 unparsed docs 及 parse_status。
- structured evidence 问题能返回 table rows/columns。
- scope / variant / conflict 行为与真实 Mining DB 的实际 relation_type 一致。

建议修复：

- 读取 `data/m1_*_corpus/questions.yaml` 中的关键用例，至少挑选 M1 contract / realistic 各 5 条做端到端断言。
- 对 `structured_evidence_lookup` 断言 evidence 中有 `structure.columns/rows`。
- 对 `source_drilldown` 断言 `relative_path/section_path/source_offsets`。
- 对 `source_audit` 断言 unparsed documents 包含 html/pdf/docx 和 processing profile。
- 对泛化问题断言 top evidence 包含关键 token，而不是只要有结果。

## 已确认的修复

以下上一轮问题已有实质改善：

- `COREMASTERKB_ASSET_DB_PATH` 已支持指向 Mining 生成的 SQLite DB，未设置时才使用 dev/test in-memory。
- `schema_adapter.py` 直接读取共享 `001_asset_core.sqlite.sql`，不再做动态转换。
- active version 读取已检查 0/1/>1。
- `EvidenceItem` 已返回 `structure` 和 `source_offsets`。
- `entity_refs_json` 读取支持 `normalized_name` 缺失时 fallback 到 `name`。
- `scope_json` 已兼容 product/products、product_version/product_versions 等 singular/plural。
- `scope_variant` 在无 scope 时不会进入普通 evidence；`conflict_candidate` 不进入普通 evidence。
- SearchRequest 已支持显式 `scope/entities/debug`。
- Normalizer 已把 SMF/UPF/AMF 等识别为 network_elements，而不是 products。
- `command-usage` 保留为兼容入口，内部仍走 QueryPlan 管线。
- 新增真实 Mining SQLite DB contract tests，证明基础读取路径可运行。

## 测试结果

运行：

```text
python -m pytest agent_serving/tests -q --ignore=agent_serving/tests/test_install_smoke.py --basetemp=.dev\pytest_serving_temp4
```

结果：

```text
72 passed
```

直接运行完整 `agent_serving/tests` 时，剩余 error 与当前环境下 pytest basetemp / install smoke 清理权限有关，不作为业务实现失败结论。

我还对真实 Mining DB 做了定向查询验证，发现 `free5GC registerIPv4/bindingIPv4` 等问题的 top evidence 明显不稳定，支撑 P1 召回质量问题。

## 回归风险

如果当前版本直接作为 M1 Serving 收口：

- Agent 可能拿到不相关 evidence，尤其是较长中文问题或包含高频虚词的问题。
- 场景/作者等非产品类 scope 被静默忽略，后续专家文档场景会出错。
- variant 选择仍偏产品中心，和通用 scope_variant 设计不完全一致。
- source_audit 无法解释未解析文件的处理状态。

## 建议修复项

建议 Claude Serving 按以下顺序修：

1. 修关键词召回与排序：停用词、有效词、候选评分、top evidence 相关性测试。
2. `QueryScope` 补 `scenarios/authors`，并同步 parse/filter/assemble。
3. scope_variant sufficient 判断改为基于实际差异维度，不只看 products。
4. drilldown scope 选择区分 missing scope 与 matched scope。
5. SourceRef/UnparsedDocument 返回 processing_profile。
6. 强化 Mining DB contract tests，接入 questions.yaml 的关键问题断言。

## 无法确认的残余风险

- 未在真实 HTTP lifespan + `COREMASTERKB_ASSET_DB_PATH` 模式下做完整服务启动验证。
- Mining 当前 semantic_role/entity_refs 仍偏弱，Serving 只能退回全文匹配；该问题需要 Mining 和 Serving 双方继续收敛。
- 未验证 PostgreSQL 版本 SQL 行为。

## 管理员介入影响

管理员要求本轮审查必须结合最新架构，重点看是否仍过度定制化、是否真正读取 Mining 数据、是否遵守 Serving 不强依赖 JSON 子字段。本文按该口径审查：不要求改表，不要求 Serving 生成最终答案，重点要求 evidence retrieval 的泛化性和真实 DB 可用性。

## 最终评估

Serving 本轮修复方向正确，已经比上一版更接近 M1 目标。但当前还不能验收为“可靠 evidence retrieval”：真实问题下召回排序过宽是主要阻塞；scope 维度和 source audit 信息也仍未完整对齐架构文档。建议继续修 P1/P2 后再复审。
