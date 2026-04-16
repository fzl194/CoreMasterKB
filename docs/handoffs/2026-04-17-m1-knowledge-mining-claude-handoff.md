# M1 Knowledge Mining Claude Handoff

> 日期: 2026-04-17
> 任务: TASK-20260415-m1-knowledge-mining
> 版本: v1.1 (基于 Codex 审查 P1-P2 修订)

## 任务目标

实现离线知识挖掘最小闭环：上游转换后 Markdown / source artifacts → L0 raw_segments → L1 canonical_segments → L2 canonical_segment_sources，写入 SQLite staging publish version。

## 实现范围

12 个 Task 全部完成：

1. **依赖安装**: markdown-it-py>=3.0
2. **数据模型**: 7 个 frozen dataclass（RawDocumentData, DocumentProfile, ContentBlock, SectionNode, RawSegmentData, CanonicalSegmentData, SourceMappingData）
3. **SQLite 适配器**: MiningDB 读取共享 `001_asset_core.sqlite.sql` DDL，提供 insert helpers
4. **文本工具**: content_hash, normalize_text, simhash_fingerprint, hamming_distance, jaccard_similarity, token_count
5. **Ingestion**: manifest.jsonl（Mode A）和纯 Markdown 目录扫描（Mode B），frontmatter 解析
6. **Document Profile**: source_type/document_type/scope_json/tags_json 分类，MML 命令检测，专家文档支持
7. **Structure Parser**: markdown-it-py + table 启用，识别 heading/table/html_table/code/list/blockquote/raw_html/unknown
8. **Segmentation**: block_type/section_role 拆分，command_name 检测，hash 计算，structure_json
9. **Canonicalization**: 三层去重（content_hash → normalized_hash → simhash+Jaccard），variant 检测
10. **Publishing**: 全量写入 SQLite（source_batch → publish_version → raw_documents → raw_segments → canonical_segments → canonical_segment_sources）
11. **Pipeline 入口**: `python -m knowledge_mining.mining.jobs.run --input <path> --db <path>`
12. **真实语料验证**: cloud_core_coldstart_md（38 docs, 620 segments, 284 canonicals）

## 不在范围内

- FastAPI / Skill / 在线检索 / context pack
- PDF/Word 解析
- embedding 生成
- 命令抽取（M2 范围）
- agent_serving 代码

## 改动文件清单

| 文件 | 说明 |
|------|------|
| `pyproject.toml` | 添加 markdown-it-py 依赖 |
| `knowledge_mining/mining/models.py` | 7 个 frozen dataclass |
| `knowledge_mining/mining/db.py` | SQLite 适配器（共享 DDL） |
| `knowledge_mining/mining/text_utils.py` | hash/normalize/simhash 工具 |
| `knowledge_mining/mining/ingestion/__init__.py` | manifest.jsonl + 纯 Markdown 导入 |
| `knowledge_mining/mining/document_profile/__init__.py` | 文档画像分类 |
| `knowledge_mining/mining/structure/__init__.py` | Markdown AST 解析 |
| `knowledge_mining/mining/segmentation/__init__.py` | L0 切分 |
| `knowledge_mining/mining/canonicalization.py` | 三层去重归并 |
| `knowledge_mining/mining/publishing/__init__.py` | SQLite 写入 |
| `knowledge_mining/mining/jobs/run.py` | Pipeline 入口 + CLI |
| `knowledge_mining/tests/test_*.py` | 71 个测试 |

## 关键设计决策

1. **SQLite 使用共享 DDL**: 读取 `knowledge_assets/schemas/001_asset_core.sqlite.sql`，不在 mining 代码中维护私有 schema
2. **source_type 映射**: manifest 中 `user_reference` 映射为 schema 有效的 `official_vendor`
3. **block_type/section_role 分离**: block_type 表示结构形态，section_role 通过标题关键词弱规则推断
4. **三层去重阈值**: simhash ≤ 3 且 Jaccard ≥ 0.85 判定为 near_duplicate

## 已执行验证

- `python -m pytest knowledge_mining/tests/ -v` → 71 passed
- `python -m knowledge_mining.mining.jobs.run --input cloud_core_coldstart_md/ --db .dev/test_coldstart.sqlite` → 成功（38 docs, 620 segments, 284 canonicals）

## 未验证项

- PostgreSQL 环境下的 schema 兼容性（仅验证了 SQLite dev 模式）
- 大规模语料（>1000 docs）下的性能和内存使用

## 已知风险

1. **section_role 推断较粗糙**: 仅基于标题关键词，可能误判。后续可引入 LLM 辅助分类。
2. **HTML table 解析**: 仅保留 raw HTML 文本，未做结构化提取。若 Serving 侧需要解析 HTML table 内容，需额外处理。
3. **SimHash 对中文敏感度**: CJK 字符逐字 tokenize 可能导致 simhash 对中文长文本区分度不足。

## Codex 审查重点

1. Schema 兼容性：是否与 v0.4 schema 完全对齐
2. source_type 映射策略是否合理
3. canonicalization 去重逻辑是否覆盖主要场景
4. Pipeline 出口数据是否能被 Serving 侧正确读取

## 管理员本轮直接介入记录

无。
