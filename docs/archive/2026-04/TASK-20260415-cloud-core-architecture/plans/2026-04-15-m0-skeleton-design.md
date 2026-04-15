# M0 项目骨架 — 设计文档

> 任务：TASK-20260415-cloud-core-architecture
> 里程碑：M0
> 作者：Claude
> 日期：2026-04-15
> 状态：用户已批准，经 Codex 反馈修订（alias_dictionary 降级）

## 1. 目标

创建新系统最小可运行骨架，验证 dev mode 能启动并返回 health。

## 2. 方案选择

| 方案 | 内容 | 选择 |
|------|------|------|
| A 最小骨架 | 目录 + pyproject.toml + FastAPI health + 规则占位 | **选中** |
| B 带 Repository | A + SQLAlchemy engine + Repository 接口 | 过早抽象 |
| C 带配置 | A + Pydantic Settings 配置体系 | M0 用不到 |

选择理由：M0 验证标准仅为 health 返回 200，不需要数据库、配置体系。后续 M1-M5 按需引入。

## 3. 目录结构

```text
Self_Knowledge_Evolve/
  pyproject.toml                          # Python >= 3.11
  .env.example                            # 环境变量模板

  scripts/
    init_db.py                            # 空占位（M1 填充）
    run_dev_demo.py                       # 空占位（M2+ 使用）

  knowledge_mining/
    mining/
      __init__.py
      ingestion/__init__.py
      document_profile/__init__.py
      structure/__init__.py
      segmentation/__init__.py
      annotation/__init__.py
      command_extraction/__init__.py
      edge_building/__init__.py
      embedding/__init__.py
      quality/__init__.py
      publishing/__init__.py
      jobs/__init__.py
    tests/__init__.py

  knowledge_assets/
    schemas/                              # 空，M1 填充 SQL
    migrations/
    dictionaries/
      README.md                           # 字典用途说明
      command_patterns.yaml               # 命令模式规则占位
      section_patterns.yaml               # 段落类型模式占位
      term_patterns.yaml                  # 术语模式占位
      builtin_alias_hints.yaml            # 内置别名提示占位
    manifests/
    samples/
      corpus_seed/
        .gitkeep
        README.md                         # 语料入口说明
      eval_questions.example.yaml         # 评测集格式示例

  agent_serving/
    serving/
      __init__.py
      main.py                             # FastAPI app 工厂
      api/
        __init__.py
        health.py                         # GET /health
      application/
        __init__.py
      retrieval/
        __init__.py
      expansion/
        __init__.py
      rerank/
        __init__.py
      evidence/
        __init__.py
      schemas/
        __init__.py
      repositories/
        __init__.py
      observability/
        __init__.py
    scripts/
      run_serving.py                      # uvicorn 启动入口
    tests/__init__.py

  skills/
    cloud_core_knowledge/
      SKILL.md                            # 空占位
```

## 4. pyproject.toml

```toml
[project]
name = "cloud-core-knowledge-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "httpx"]
```

## 5. Health Endpoint

```python
# agent_serving/serving/api/health.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
```

## 6. 启动方式

```bash
python -m agent_serving.scripts.run_serving
# curl http://127.0.0.1:8000/health → {"status": "ok", "version": "0.1.0"}
```

## 7. 规则配置占位（替代原 alias_dictionary）

> **Codex 反馈修订**: `old/ontology` 中的云核心网本体不可靠，不能作为正式 alias_dictionary 的来源。M0 不生成正式 alias_dictionary，改为创建规则配置占位和语料入口说明。正式 alias 候选抽取放到 M2/M3，从用户导入的 Markdown 产品文档中自动生成。

M0 创建以下占位文件：

- `knowledge_assets/dictionaries/README.md` — 字典用途说明
- `knowledge_assets/dictionaries/command_patterns.yaml` — 命令识别规则占位
- `knowledge_assets/dictionaries/section_patterns.yaml` — 段落类型规则占位
- `knowledge_assets/dictionaries/term_patterns.yaml` — 术语识别规则占位
- `knowledge_assets/dictionaries/builtin_alias_hints.yaml` — 内置别名提示占位（非正式字典，仅作开发参考）
- `knowledge_assets/samples/corpus_seed/.gitkeep` — 语料入口
- `knowledge_assets/samples/corpus_seed/README.md` — 语料入口说明
- `knowledge_assets/samples/eval_questions.example.yaml` — 评测集格式示例

## 8. 不做的事

- 不建数据库表
- 不引入 SQLAlchemy
- 不搭配置体系（Pydantic Settings）
- 不写测试（M0 没有 logic 可测）
- 不写 run_dev_demo.py 的实际逻辑

## 9. 验证标准

```bash
pip install -e .
python -m agent_serving.scripts.run_serving
curl http://127.0.0.1:8000/health
# 预期: {"status": "ok", "version": "0.1.0"}
```
