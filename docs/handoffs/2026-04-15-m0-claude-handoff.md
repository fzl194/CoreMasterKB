# M0 Skeleton Handoff — Claude → Codex

> 修订说明：2026-04-17 | Claude | 初版 handoff
> 状态：已审查（Codex review: `docs/analysis/2026-04-15-m0-skeleton-codex-review.md`；需要 Claude 修复后回交）

## 任务目标

创建最小可运行的项目骨架，使 `GET /health` 返回 200。不建库、不搭配置体系、无 ML 依赖。

## 本次实现范围

1. 单 `pyproject.toml`（FastAPI + uvicorn + pydantic 依赖）
2. 完整目录骨架（knowledge_mining / knowledge_assets / agent_serving / skills / scripts）
3. FastAPI app + health endpoint + 异步测试
4. Serving 启动入口（`agent_serving/scripts/run_serving.py`）
5. 规则配置占位文件（dictionaries/）
6. 语料入口说明 + 评测示例（samples/）
7. 环境变量模板 + 占位脚本 + Skill 占位

## 明确不在本次范围内的内容

- 数据库 schema 创建（M1）
- 配置体系（M1）
- 挖掘态 pipeline（M2+）
- alias_dictionary 生成（M2/M3，从用户导入的 Markdown 抽取）
- API v1 端点（M4+）
- Skill 实现（M6）

## 改动文件清单

| 文件 | 用途 |
|------|------|
| `pyproject.toml` | 项目配置与依赖 |
| `agent_serving/serving/main.py` | FastAPI app |
| `agent_serving/serving/api/health.py` | health endpoint |
| `agent_serving/tests/test_health.py` | 异步 health 测试 |
| `agent_serving/scripts/run_serving.py` | uvicorn 启动入口 |
| `knowledge_assets/dictionaries/README.md` | 字典目录说明与系统约束 |
| `knowledge_assets/dictionaries/command_patterns.yaml` | 命令识别规则占位 |
| `knowledge_assets/dictionaries/section_patterns.yaml` | 段落类型识别规则占位 |
| `knowledge_assets/dictionaries/term_patterns.yaml` | 术语识别规则占位 |
| `knowledge_assets/dictionaries/builtin_alias_hints.yaml` | 别名提示占位 |
| `knowledge_assets/samples/corpus_seed/README.md` | 语料入口说明 |
| `knowledge_assets/samples/corpus_seed/.gitkeep` | 目录占位 |
| `knowledge_assets/samples/eval_questions.example.yaml` | 评测格式示例 |
| `.env.example` | 环境变量模板 |
| `scripts/init_db.py` | DB 初始化占位 |
| `scripts/run_dev_demo.py` | 开发 demo 占位 |
| `skills/cloud_core_knowledge/SKILL.md` | Skill 占位 |
| 所有 `__init__.py` | 包结构 |

## 关键设计决策

1. **单 pyproject.toml**：不拆分为独立包，所有模块在同一仓库
2. **build-backend = setuptools.build_meta**：修复了 Codex 初始版本的 backend 错误
3. **No Neo4j / No ontology dependency**：系统不依赖预置本体启动
4. **No alias_dictionary in M0**：遵照 Codex 反馈，改为规则配置占位

## 已执行验证

- `pip install -e ".[dev]"` — 成功安装
- `pytest agent_serving/tests/test_health.py` — 1 passed
- `python -m agent_serving.scripts.run_serving` + `curl /health` — `{"status":"ok","version":"0.1.0"}`
- 目录结构完整：46 个文件

## 未验证项

- Windows 以外平台的兼容性（未测试 Linux/macOS）
- Python 3.11 最低版本兼容性（开发环境为 3.12.7）

## 已知风险

1. `pytest-asyncio` 的 `asyncio_mode = strict` 要求所有异步测试标记 `@pytest.mark.asyncio`，后续测试需注意
2. `command_patterns.yaml` 等占位文件为空数组，M2/M3 填充时需确认规则格式与 mining pipeline 的对接方式

## 指定给 Codex 的审查重点

1. **目录结构**：是否与架构文档 `docs/architecture/2026-04-15-cloud-core-agent-knowledge-architecture.md` §4 一致
2. **pyproject.toml**：依赖版本约束是否合理，build-backend 是否正确
3. **dictionaries/README.md 约束**：系统不依赖预置本体启动的约束是否已清晰表达
4. **测试结构**：async health test 的写法是否规范
5. **遗漏文件**：是否有 M0 骨架阶段应包含但遗漏的文件
