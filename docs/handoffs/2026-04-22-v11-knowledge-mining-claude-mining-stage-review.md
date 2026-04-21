# v1.1 Knowledge Mining Pipeline 逐阶段审查报告

- 时间：2026-04-22
- Author：Claude Mining
- 关联任务：TASK-20260421-v11-knowledge-mining
- 关联消息：MSG-20260422-003000-claude-mining
- 审查范围：`knowledge_mining/mining/` 全部 10 个 pipeline stage
- 审查方法：逐阶段读取源码，记录功能、逻辑、问题与反思

---

## 审查总表

| Stage | 模块 | CRITICAL | HIGH | MEDIUM | LOW |
|-------|------|----------|------|--------|-----|
| 1. Ingest | ingestion | 0 | 0 | 2 | 0 |
| 2. Parse | parsers | 0 | 0 | 2 | 0 |
| 3. Structure | structure | 0 | 0 | 2 | 2 |
| 4. Segment | segmentation | 0 | 0 | 2 | 2 |
| 5. Enrich | enrich | 0 | 0 | 2 | 1 |
| 6. Relations | relations | 0 | 1 | 1 | 1 |
| 7. Retrieval Units | retrieval_units | 0 | 0 | 2 | 1 |
| 8. Snapshot | snapshot | 0 | 1 | 1 | 1 |
| 9. Build | publishing/assemble | 0 | 1 | 1 | 1 |
| 10. Publish | publishing/release | 0 | 0 | 1 | 1 |
| **合计** | | **0** | **3** | **16** | **11** |

---

## Stage 1: Ingest（摄入）

**模块路径：** `knowledge_mining/mining/ingestion/__init__.py`

**做什么：** 递归扫描输入目录，按扩展名识别文件类型，对每个文件计算 raw_hash（原始 SHA256）和 normalized_content_hash（保守归一化：CRLF→LF + 去尾空白 + 去空行 → SHA256），产出 `RawFileData` 列表。

**具体流程：**
1. `_walk_directory()` 递归扫描，`_should_skip()` 过滤隐藏文件/目录
2. `_classify_file()` 按扩展名映射文件类型（md, txt, docx, pdf 等）
3. `_read_and_hash()` 读取文件内容，计算 dual hash
4. 非可解析文件（docx/pdf 等）使用 raw_hash 作为 normalized_content_hash fallback
5. 构建 `RawFileData` frozen dataclass，包含 scope_json（从路径推断设备型号）

**问题：**

| 级别 | 问题 | 说明 |
|------|------|------|
| MEDIUM | skip 名称覆盖不全 | `_should_skip()` 仅检查以 `.` 开头的文件/目录，不覆盖 `__pycache__`、`node_modules`、`~` 前缀临时文件等常见跳过场景 |
| MEDIUM | 大文件内存风险 | `_read_and_hash()` 对整个文件做一次性 `read_bytes()`，对于超大文件（如几百 MB 的 PDF）会占用大量内存 |

---

## Stage 2: Parse（解析）

**模块路径：** `knowledge_mining/mining/parsers/__init__.py`

**做什么：** 按文件类型选择解析器，将文件内容转为 SectionNode 树。

**具体流程：**
1. `create_parser(file_type)` 工厂方法，当前支持 MarkdownParser、PlainTextParser、PassthroughParser
2. **MarkdownParser** — 调用 `structure.parse_structure()` 得到 SectionNode 树
3. **PlainTextParser** — 按 300 token 分块（30 token overlap），每块构造为 SectionNode
4. **PassthroughParser** — 返回 None（跳过不支持的格式）

**问题：**

| 级别 | 问题 | 说明 |
|------|------|------|
| MEDIUM | CJK 分词偏差 | PlainTextParser 使用 `token_count()` 估算 token 数（空格分割），对中文/日文等 CJK 文本不准确——CJK 文本没有空格分隔，会低估 token 数 |
| MEDIUM | 尾部短块 | PlainTextParser 的 overlap 机制可能导致最后一个块非常短（< 30 token），没有合并到前一个块的逻辑 |

---

## Stage 3: Structure（结构解析）

**模块路径：** `knowledge_mining/mining/structure/__init__.py`

**做什么：** 将 Markdown 文本解析为 SectionNode 树 + ContentBlock 列表，保持层级关系。

**具体流程：**
1. `parse_structure(content)` → `MarkdownIt().enable("table")` 解析 tokens
2. `_tokens_to_blocks()` 逐 token 分类转为 ContentBlock：heading（带 level）、table（提取 columns/rows）、code（带 language）、list（带 items 和 structure）、blockquote、html_block（区分 html_table 和 raw_html）、paragraph
3. `_build_section_tree()` → 按 min_level heading 分割成 top sections
4. `_build_nested_section()` → 递归嵌套子 section
5. `_split_sub_sections()` → 按 heading level 降级分割

**问题：**

| 级别 | 问题 | 说明 |
|------|------|------|
| MEDIUM | 嵌套列表丢失子级 | `_tokens_to_blocks()` 中 `depth == 1` 只取顶层 inline，嵌套列表的子项被丢弃 |
| MEDIUM | 单 section 优化有损语义 | `_build_section_tree()` 中如果只有一个 top section，直接提为 root。但 pre_blocks 会拼到 root.blocks 上，语义上 pre_blocks 是 H1 之前的无标题内容 |
| LOW | html_table 不提取结构 | 检测到 `<table` 但只存为 html_table 文本，不提取 columns/rows |
| LOW | heading 降级跳跃不处理 | 如 H1 直接到 H3（跳过 H2），`_split_sub_sections` 仍按 > parent_level 分割，层级关系不够精确 |

**总体评价：** Structure 模块实现稳定，覆盖了 Markdown 主要元素类型，表格结构保留完整。嵌套列表信息丢失是当前最大短板，但对网络设备文档场景影响有限——这类文档以 heading + table + paragraph + code 为主。

---

## Stage 4: Segment（分切）

**模块路径：** `knowledge_mining/mining/segmentation/__init__.py`

**做什么：** 将 SectionNode 树遍历，按规则切分为 RawSegmentData 列表。

**具体规则：**
1. 每个 section title → 独立 heading segment（用于后续 `section_header_of` relation）
2. table / code / list / blockquote → 各自独立一个 segment
3. 连续 paragraph → 合并为一个 segment
4. 遇到 heading 时 flush 当前 current_group
5. segment_index 最终统一重编号

**问题：**

| 级别 | 问题 | 说明 |
|------|------|------|
| MEDIUM | normalized_text 粗糙 | `_make_segment()` 中 `raw_text.lower().strip()` 只做了小写+去首尾空白，没有标点归一化、全角半角统一。和 hash_utils 的 conservative normalization 不一致 |
| MEDIUM | 多 paragraph 合并无上限 | 连续 paragraph 全部合并到一个 segment，如果出现 10 段连续段落，会生成超大 segment。没有 token 上限切分 |
| LOW | section_title 对 heading segment 语义冗余 | heading segment 的 section_title 和 raw_text 相同，但非 heading segment 的 section_title 取 section.title（可能为 None） |
| LOW | _extract_structure_info 多 block 覆盖 | 如果 segment 包含多个 table，`info.update()` 后者覆盖前者 |

**总体评价：** Segment 逻辑清晰，heading 独立落库的设计对后续 relation 构建很有利。最大问题是多 paragraph 无上限合并，对我们的文档影响不大（网络设备文档以 table + code + list 为主）。

---

## Stage 5: Enrich（理解增强）

**模块路径：** `knowledge_mining/mining/enrich/__init__.py`

**做什么：** 正式可替换理解阶段。v1.1 用 rule-based，v1.2 可注入 LLM 实现。

**对每个 segment 做 4 件事：**
1. Entity extraction — `RuleBasedEntityExtractor.extract()` 从 raw_text + section_path 提取命令、网元、参数
2. Section-title entities — 从 section_title 正则匹配命令模式（如 `ADD NE`、`SHOW NE`）
3. Role classification — `DefaultRoleClassifier.classify()` 基于 raw_text + section_title + block_type 判定语义角色
4. Metadata enrichment — heading_role、table_column_count、table_has_parameter_column

**关键设计：** EntityExtractor / RoleClassifier / Enricher 三个 Protocol 接口，RuleBasedEnricher 接受可替换实现。segmentation 不再包含任何理解逻辑。

**问题：**

| 级别 | 问题 | 说明 |
|------|------|------|
| MEDIUM | enrich 无 batch 语义 | `enrich()` 逐 segment 处理，无法利用上下文（前后 segment 关系）。LLM 实现通常需要 batch + context window |
| MEDIUM | heading_role 与 semantic_role 重叠 | `_classify_heading_role()` 输出到 metadata，但 semantic_role 也可能分类为同类概念，两套分类体系可能冲突 |
| LOW | _HEADING_ROLE_KEYWORDS 硬编码中文 | 关键词全是中文（"参数"、"示例"等），不支持英文文档 |

---

## Stage 6: Build Relations（关系构建）

**模块路径：** `knowledge_mining/mining/relations/__init__.py`

**做什么：** 从有序 segment 列表构建结构关系，4 种关系类型。

**具体逻辑：**
1. previous/next — 顺序相邻，双向，distance=1
2. same_section — 共享 section_path 的 segment 间两两关系，distance 为位置差
3. section_header_of — heading segment → 同 section 内所有非 heading segment
4. same_parent_section — 共享 parent section 的 segment 间关系（>2 个才建）

**问题：**

| 级别 | 问题 | 说明 |
|------|------|------|
| HIGH | same_section O(n²) 爆炸 | 如果一个大 section 下有 100 个 segment，会生成 C(100,2)=4950 条关系。对网络设备文档常见的大参数表场景，关系数可能膨胀严重 |
| MEDIUM | previous/next 不区分 section 边界 | section 最后一个 segment 和下一个 section 第一个 segment 也建立 previous/next 关系，但实际上它们可能属于完全不同的语义域 |
| LOW | same_parent_section 阈值硬编码 | `len(seg_keys) > 2`，3 个以上才建关系，这个阈值没有配置化 |

**总体评价：** 关系构建逻辑正确，4 种类型覆盖了文档结构的主要关联方式。same_section O(n²) 是最大隐患，需要考虑加 distance 上限或 segment 数量上限来控制关系总数。

---

## Stage 7: Build Retrieval Units（检索单元构建）

**模块路径：** `knowledge_mining/mining/retrieval_units/__init__.py`

**做什么：** 从 enriched segments 构建多种类型的检索单元。

**4 种检索单元：**
1. raw_text — 1:1 映射每个 segment，weight=1.0
2. contextual_text — segment 原文前拼接 section path 上下文（如 `[概述 > 参数说明]\n...`），weight=0.9
3. entity_card — 每个 unique entity 一张卡（全局去重），weight=0.5
4. generated_question — LLM 生成的检索用问题，v1.1 用 NoOp 返回空，weight=0.7

**问题：**

| 级别 | 问题 | 说明 |
|------|------|------|
| MEDIUM | entity_card 只记录 first_seen_in | 如果同一 entity 出现在多文档，entity_card 只记录第一次见到的文档。跨文档 entity 合并是 v1.3 的范围 |
| MEDIUM | entity_card 去重范围是单文档 | `seen_entity_cards` 是内存 set，只在单次 `build_retrieval_units` 调用内去重。不同文档各自调用一次，意味着同一 entity 在不同文档中仍会各建一张 card |
| LOW | contextual_text 对 heading 跳过 | heading 不生成 contextual_text，但 heading 本身也可以被检索到（通过 raw_text unit）。这导致 heading 只有裸文本，没有上下文信息 |

**总体评价：** 检索单元设计合理，4 种类型覆盖了不同检索场景。QuestionGenerator Protocol 为 LLM 接入留了干净接口。entity_card 去重范围是当前最大限制，但这是设计上的权衡——跨文档去重需要全局状态，v1.3 再解决。

---

## Stage 8: Select Snapshot（快照选择）

**模块路径：** `knowledge_mining/mining/snapshot/__init__.py`

**做什么：** 实现三层模型——document（身份）→ snapshot（共享内容）→ link（映射）。

**具体逻辑：**
1. 按 document_key 查找已有 document，复用其 id
2. 按 normalized_content_hash 查找已有 snapshot，内容相同则复用
3. 始终创建新 link（记录本次摄入事件）

**问题：**

| 级别 | 问题 | 说明 |
|------|------|------|
| HIGH | snapshot 复用与 segments 写入一致性 | snapshot 模块只管三层模型创建，segments/relations/retrieval_units 的写入在 run.py 中 snapshot 之后。如果 snapshot 已存在（内容没变），但 pipeline 仍然跑了 segment→enrich→relations→retrieval_units，可能写入重复 segments。当前 run.py 的 SKIP 分支覆盖了内容不变的场景 |
| MEDIUM | snapshot 复用时旧 segments 是否该复用 | 如果 snapshot 已存在，说明旧 segments 还在。当前 upsert 语义可能导致同一 snapshot 下出现重复 segment 数据 |
| LOW | link 始终新建 | 每次摄入同一文档都新建 link。这用于追踪摄入历史是合理的，但 link 的唯一性约束没有明确 |

---

## Stage 9: Assemble Build（构建组装）

**模块路径：** `knowledge_mining/mining/publishing/__init__.py` — `assemble_build()`

**做什么：** 将 snapshot decisions 组装成 build，支持 full/incremental 两种模式。

**具体流程：**
1. `classify_documents()` — 对比 prev active build，给每个 document 标记 NEW/UPDATE/SKIP/REMOVE
2. `determine_build_mode()` — 有 prev build → incremental，无 → full
3. `assemble_build()` — 创建 build record + 增量合并（carry forward parent snapshots not in current decisions）+ 写入当前 decisions
4. 自动标记为 validated

**问题：**

| 级别 | 问题 | 说明 |
|------|------|------|
| HIGH | validate 是空操作 | `asset_db.update_build_status(build_id, "validated")` 直接从 building → validated，中间没有任何校验逻辑。build 里可能没有任何 snapshot（空 build），也会被标记为 validated |
| MEDIUM | REMOVE 决策缺少实际执行 | classify_documents() 会标记 REMOVE action，但 assemble_build() 只是把 REMOVE 的 document 不写入 build_document_snapshot。并没有真正从 asset core 中移除 document 或 snapshot。REMOVE 只是"不出现在 build 中" |
| LOW | incremental merge 不检查 snapshot 有效性 | carry forward parent snapshots 时，假设 parent 的 snapshot 仍然有效 |

---

## Stage 10: Publish Release（发布）

**模块路径：** `knowledge_mining/mining/publishing/__init__.py` — `publish_release()`

**做什么：** 将 validated build 激活为当前 release。

**具体流程：**
1. 检查 build 状态必须是 validated 或 published
2. 查找当前 active release 作为 previous
3. 创建新 release record（status=staging）
4. `activate_release()` — 退休旧 release，激活新 release

**问题：**

| 级别 | 问题 | 说明 |
|------|------|------|
| MEDIUM | activate_release 原子性不透明 | `asset_db.activate_release(release_id)` 是 DB 层操作，具体逻辑不在 publishing 模块可见范围内。需确认 DB 层是否用了事务保证原子性 |
| LOW | staging → active 瞬间完成 | release 创建时 status=staging，然后立即 activate。没有真正的 staging 阶段用于验证或灰度 |

---

## 3 个 HIGH 问题详细分析与建议

### HIGH-1: Relations same_section O(n²) 爆炸

**位置：** `relations/__init__.py` 第 82-89 行

**现状：** 同一 section 下所有 segment 两两建关系，O(n²) 增长。

**影响：** 网络设备文档中"参数说明"section 可能包含几十行参数表格，每个参数是一个 segment，关系数会急剧膨胀。

**建议修复：** 加 distance 上限（如 distance ≤ 5），只对近距离 segment 建关系。远距离的可以通过 section_header_of + previous/next 间接到达。

### HIGH-2: Snapshot 复用与 Segments 一致性

**位置：** `snapshot/__init__.py` + `jobs/run.py`

**现状：** run.py 的 SKIP 分支在内容不变时跳过整个 pipeline（包括 snapshot 创建），避免了重复 segments。但如果 snapshot 已存在且内容确实变了（UPDATE），旧 segments 可能残留。

**影响：** 当前 pipeline 中 UPDATE 场景下，新 segments 会写入同一 snapshot_id。如果 `insert_raw_segment` 没有 UPSERT 语义，会出现重复；如果有 UPSERT 语义，则覆盖旧数据。

**建议修复：** 在 UPDATE 场景下，写入新 segments 前先清理该 snapshot_id 下的旧 segments。

### HIGH-3: Build Validate 空操作

**位置：** `publishing/__init__.py` 第 143 行

**现状：** `update_build_status(build_id, "validated")` 没有任何前置检查。

**影响：** 空 build（没有任何 snapshot）也会通过验证并可能被发布。

**建议修复：** 在 validated 前加基本检查：build 至少有 1 个 active snapshot；incremental build 的 parent build 必须存在。

---

## 演进建议

1. **v1.2 优先：** Relations O(n²) 修复 + Build validate 加固
2. **v1.2 LLM 接入：** EntityExtractor/RoleClassifier/QuestionGenerator 三个 Protocol 已就位，直接注入 LLM 实现
3. **v1.3 跨文档：** entity_card 全局去重 + 跨文档实体合并
4. **通用改进：** normalized_text 归一化策略统一、多 paragraph 合并上限、CJK token 估算修正
