# TASK-20260421-v11-knowledge-mining Codex Review

## 审查背景

- 任务：`TASK-20260421-v11-knowledge-mining`
- 审查对象：Claude Mining 提交的 v1.1 `knowledge_mining/` 重构实现、对应 plan/handoff、与 `asset_core` / `mining_runtime` 契约的一致性
- 审查基线：
  - `docs/architecture/2026-04-21-coremasterkb-v1.1-architecture.md`
  - `docs/plans/2026-04-21-v11-knowledge-mining-impl-plan.md`
  - `docs/handoffs/2026-04-21-v11-knowledge-mining-claude-mining-handoff.md`
  - `databases/asset_core/schemas/001_asset_core.sqlite.sql`
  - `databases/mining_runtime/schemas/001_mining_runtime.sqlite.sql`
  - 提交链：`037703f` 到 `9fae2be`

## 审查范围

- `knowledge_mining/mining/` 主链：ingestion / parsers / structure / segmentation / enrich / relations / retrieval_units / snapshot / publishing / runtime / jobs
- `knowledge_mining/README.md`
- `knowledge_mining/tests/` 中 v1.1 相关测试与残留测试状态
- plan / handoff / 最终代码的一致性

## 发现的问题

### P1. LLM 演进接缝没有落在 `enrich`，理解逻辑仍然写死在 `segmentation`，后续无法低成本接入统一 LLM Runtime

- plan 明确要求：`enrich` 是正式 pipeline 阶段，具备 Protocol 接口，v1.1 rule-based，v1.2 可直接替换为 LLM 实现。
- 实际代码中，`RuleBasedEntityExtractor` 与 `DefaultRoleClassifier` 在 `run.py` 中被直接实例化，并在 `segment_document()` 阶段完成 `entity_refs_json` 与 `semantic_role` 的主判定。
- `enrich_segments()` 只做 section title 补实体和 metadata 修饰，没有承担可替换的“理解阶段”职责，也没有为 LLM Runtime 预留统一 client / response 合同。
- 这会导致后续接 LLM 时不得不改 `segmentation` 主链，而不是只替换 `enrich` provider，违背了本轮“先搭可演进骨架”的目标。
- 代码位置：
  - `knowledge_mining/mining/jobs/run.py:170`
  - `knowledge_mining/mining/jobs/run.py:171`
  - `knowledge_mining/mining/jobs/run.py:219`
  - `knowledge_mining/mining/jobs/run.py:220`
  - `knowledge_mining/mining/segmentation/__init__.py:46`
  - `knowledge_mining/mining/segmentation/__init__.py:203`
  - `knowledge_mining/mining/segmentation/__init__.py:208`
  - `knowledge_mining/mining/enrich/__init__.py:14`
- 文档位置：
  - `docs/plans/2026-04-21-v11-knowledge-mining-impl-plan.md:85`
  - `docs/plans/2026-04-21-v11-knowledge-mining-impl-plan.md:88`
  - `docs/plans/2026-04-21-v11-knowledge-mining-impl-plan.md:208`
  - `docs/plans/2026-04-21-v11-knowledge-mining-impl-plan.md:263`
  - `docs/plans/2026-04-21-v11-knowledge-mining-impl-plan.md:302`

### P1. Retrieval units 已偏离计划承诺，`generated_question` 未交付，Mining 仍未形成对接 LLM Runtime 的正式入口

- plan 将 v1.1 retrieval unit 定义为 `raw_text + contextual_text + generated_question`，其中 `generated_question` 允许在 LLM Runtime 不可用时跳过，但必须保留这条可接入路径；`entity_card` 被放在 v1.2。
- 实际实现、README 与 handoff 都把 v1.1 改成了 `raw_text + contextual_text + entity_card`，完全没有 `generated_question` 生成器、协议或弱引用落库路径。
- 这意味着当前 Mining 没有提供任何真正面向 LLM Runtime 的第一批接入点，后续无法按你当前要求“等 LLM 字段明确后快速同步上”。
- 代码位置：
  - `knowledge_mining/mining/retrieval_units/__init__.py:3`
  - `knowledge_mining/mining/retrieval_units/__init__.py:41`
  - `knowledge_mining/mining/retrieval_units/__init__.py:46`
- 文档位置：
  - `docs/plans/2026-04-21-v11-knowledge-mining-impl-plan.md:17`
  - `docs/plans/2026-04-21-v11-knowledge-mining-impl-plan.md:152`
  - `docs/plans/2026-04-21-v11-knowledge-mining-impl-plan.md:154`
  - `docs/plans/2026-04-21-v11-knowledge-mining-impl-plan.md:210`
  - `knowledge_mining/README.md:29`
  - `knowledge_mining/README.md:100`
  - `docs/handoffs/2026-04-21-v11-knowledge-mining-claude-mining-handoff.md:67`

### P1. Build / release 仍是“全量重建”实现，没有兑现计划中的 merge build 语义与文档级变更集抽象

- plan 与任务 briefing 都要求：新 build = 上一个 active build + 本轮变更集，并显式区分 `NEW / UPDATE / SKIP / REMOVE`。
- 实际代码中，每个文档在 run 时一律登记为 `action="NEW"`；`snapshot_decisions` 只记录 `reason="add"`；`assemble_build()` 调用被固定为 `build_mode="full"`。
- `publishing/assemble_build()` 里虽然写了 incremental retain 分支，但当前主链永远走不到，因此 build/release 语义仍是“按本次输入目录重建一版”，不是正式架构要求的 build 视图合成。
- 这会直接影响 Serving 对 active build 的稳定预期，也让后续增量 Mining / 断点续跑 / 发布控制失去基础。
- 代码位置：
  - `knowledge_mining/mining/jobs/run.py:188`
  - `knowledge_mining/mining/jobs/run.py:321`
  - `knowledge_mining/mining/jobs/run.py:339`
  - `knowledge_mining/mining/jobs/run.py:346`
  - `knowledge_mining/mining/publishing/__init__.py:20`
  - `knowledge_mining/mining/publishing/__init__.py:33`
  - `knowledge_mining/mining/publishing/__init__.py:54`
- 文档位置：
  - `docs/plans/2026-04-21-v11-knowledge-mining-impl-plan.md:167`
  - `docs/plans/2026-04-21-v11-knowledge-mining-impl-plan.md:240`
  - `docs/plans/2026-04-21-v11-knowledge-mining-impl-plan.md:243`
  - `docs/handoffs/2026-04-21-v11-knowledge-mining-claude-mining-handoff.md:85`

### P1. Run 失败语义不正确：全局异常不会把 run 标记为 failed，局部失败也仍可能发布部分语料

- `run()` 外层异常处理没有调用 `tracker.fail_run()`，只尝试 `runtime_db.commit()` 后重新抛错；因此全局阶段异常时，`mining_runs.status` 可能停留在 `running`。
- 文档级失败只会累加 `failed_count`，但只要仍有 `snapshot_decisions`，Phase 2 仍会继续 assemble + publish。
- 最终 `tracker.complete_run()` 无条件把 run 标记为 `completed`，即使 `failed_count > 0`。
- 这意味着当前系统允许“部分文档失败 + 仍发布 active release”，不符合正式资产生产链对可追溯和可恢复的要求，也会让 Serving 读到一版掺杂失败遗漏的 build。
- 代码位置：
  - `knowledge_mining/mining/jobs/run.py:72`
  - `knowledge_mining/mining/jobs/run.py:76`
  - `knowledge_mining/mining/jobs/run.py:330`
  - `knowledge_mining/mining/jobs/run.py:339`
  - `knowledge_mining/mining/jobs/run.py:370`

### P2. 仓库迁移未收干净，旧 v0.5 测试与接口残留会误导“30 tests passed”的有效性判断

- 当前 `knowledge_mining/tests/` 中仍残留大量 v0.5 测试文件，引用 `MiningDB`、`run_pipeline`、`canonicalization`、`document_profile`、`CanonicalSegmentData`、`NoOpSegmentEnricher` 等已不存在对象。
- 我实际导入验证这些名称，当前 v1.1 模块中均不存在。
- 这说明仓库还处于半迁移状态，`30 tests passed` 只覆盖新建的一组 v1.1 测试，不能代表 `knowledge_mining/tests/` 整体可用，也会干扰后续协作者判断真实回归面。
- 证据位置：
  - `knowledge_mining/tests/test_db.py:1`
  - `knowledge_mining/tests/test_pipeline.py:8`
  - `knowledge_mining/tests/test_corpus_verification.py:7`
  - `knowledge_mining/tests/test_document_profile.py:4`
  - `knowledge_mining/tests/test_extractors.py:9`
  - `knowledge_mining/tests/test_models.py:10`

### P2. DB 适配器没有创建父目录，路径健壮性弱于同仓库其他新模块

- `knowledge_mining/mining/db.py` 的 `_DB.open()` 直接 `sqlite3.connect()`，没有像 `llm_service/db.py` 一样先创建 `db_path` 父目录。
- 在当前环境中，`test_v11_pipeline.py` 的大量用例因为临时目录权限问题失败；虽然这不是纯代码缺陷的唯一原因，但 `AssetCoreDB` / `MiningRuntimeDB` 的路径创建缺失会放大实际部署与测试路径差异。
- 代码位置：
  - `knowledge_mining/mining/db.py:68`
  - `knowledge_mining/mining/db.py:71`
  - `llm_service/db.py:16`

## 测试缺口

- 当前未看到覆盖“部分文档失败时 run / build / release 应如何收口”的测试。
- 当前未看到覆盖 LLM 接口预留的测试，因为实际并未交付 `generated_question` 或 LLM-backed enrich 接口。
- 当前未看到覆盖 `NEW / UPDATE / SKIP / REMOVE` 变更集与 incremental build 的测试，因为实际主链固定为 `full`。
- 我执行 `python -m pytest knowledge_mining/tests/test_v11_pipeline.py -q` 时，除了当前机器临时目录权限 `WinError 5` 外，也观察到仓库仍存在大量残留 v0.5 测试文件引用已删除接口，说明“30 tests passed”仅能证明新子集，而不能证明整个测试目录已收口。

## 回归风险

- 若现在直接让 Serving 建立在这套 build/release 语义上，后续切回真正的 incremental build 时会出现读取契约变化。
- 若现在继续把理解逻辑写死在 `segmentation`，后面接 LLM Runtime 会牵动 `segment -> enrich -> retrieval_units` 三段，而不是局部替换。
- 若 run 在部分失败时仍然发布，active release 可能长期带着静默缺失文档。
- 若不清理旧测试与旧接口残留，后续协作者会误判回归面和真实可运行边界。

## 建议修复项

1. 先把“实体抽取 + 角色分类 + 生成型 retrieval units”抽成正式可替换接口，收口到 `enrich` / `retrieval_units` 两段，并明确等待 LLM Runtime 的统一返回字段。
2. 恢复 plan 的 v1.1 retrieval 口径：至少把 `generated_question` 预留成正式生成器与落库路径，哪怕 Runtime 不可用时返回空。
3. 把 run 的文档 action 与 build merge 语义真正落地：
   - 识别 `NEW / UPDATE / SKIP / REMOVE`
   - build 选择逻辑基于上一个 active build
   - 不再固定 `build_mode="full"`
4. 修正 run 状态机：
   - 全局异常必须 `fail_run()`
   - 局部失败时是否允许发布需要明确策略；默认应阻断 active release，或至少将 run 标为 failed / interrupted
5. 清理或归档残留 v0.5 测试与接口引用，保证 `knowledge_mining/tests/` 的基线与 v1.1 一致。
6. 为 DB adapter 补齐父目录创建逻辑，减少路径环境差异。

## 无法确认的残余风险

- 当前环境对临时目录存在广泛 `WinError 5` 权限问题，导致无法在本机完整复跑全部 v1.1 pytest 用例；因此对部分行为只能结合代码与测试文件静态审查。
- 未对真实大语料、长文档和并发写入做端到端验证。

## 管理员介入影响

- 用户已明确要求本轮审查不能停留在 rule-based 基线，而要推动 Mining 往 LLM 演进方向走。
- 因此本次 review 将“LLM 接缝未建立”视为主问题，而不是未来增强建议。

## 最终评估

- 当前 `knowledge_mining` 已经摆脱旧 canonical 主链，完成了双库分层和 shared snapshot / build / release 的基础骨架。
- 但它还没有达到“可快速接入统一 LLM Runtime、并稳定服务 Serving”的阶段。
- 结论：**存在需要 Claude 修复的实质问题，尤其是 LLM 演进接缝、build 语义和 run 失败语义，当前不建议将其视为可演进闭环实现。**
