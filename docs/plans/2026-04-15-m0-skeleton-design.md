# M0 项目骨架 — 设计文档

> 任务：TASK-20260415-cloud-core-architecture
> 里程碑：M0
> 作者：Claude
> 日期：2026-04-15
> 状态：用户已批准

## 1. 目标

创建新系统最小可运行骨架，验证 dev mode 能启动并返回 health。

## 2. 方案选择

| 方案 | 内容 | 选择 |
|------|------|------|
| A 最小骨架 | 目录 + pyproject.toml + FastAPI health + alias_dictionary.yaml | **选中** |
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
    dictionaries/alias_dictionary.yaml    # 从 old/ontology 提取初版
    manifests/
    samples/

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

## 7. alias_dictionary.yaml

从 `old/ontology/domains/cloud_core_network.yaml` 提取所有 NF 的 `canonical_name`、`display_name_zh`，补充业务同义词（APN↔DNN、N4↔PFCP 等）。约 20-30 条初始条目。

格式：

```yaml
entries:
  - canonical: AMF
    zh: 接入和移动性管理功能
    aliases: [Access and Mobility Management Function, AMF功能, 接入移动管理]
    category: nf
```

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
