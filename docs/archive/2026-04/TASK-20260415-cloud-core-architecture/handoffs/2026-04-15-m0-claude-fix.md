# M0 Fix Document — Claude → Codex

> 日期：2026-04-15
> 关联审查：`docs/archive/2026-04/TASK-20260415-cloud-core-architecture/analysis/2026-04-15-m0-skeleton-codex-review.md`
> 修复人：Claude

## 修复项

### P1: pyproject.toml package discovery 返回空列表

- **根因**：缺少 `agent_serving/__init__.py`、`agent_serving/scripts/__init__.py`、`knowledge_mining/__init__.py`
- **修复**：补齐 3 个 `__init__.py` 文件
- **验证**：`find_packages(include=['agent_serving*','knowledge_mining*'])` 现在返回 26 个包
- **新增**：`agent_serving/tests/test_install_smoke.py` — 从临时目录外执行 import 验证
- **提交**：`b7f8910` `[claude]: fix P1 — add missing top-level __init__.py + install smoke test`

### P2: 架构基线残留旧 M0 说明

- **根因**：M0 里程碑仍写"补充 alias_dictionary.yaml（从 old/ontology 抽取）"，dev mode 入口仍写 `agent_serving.serving.run`
- **修复**：
  - M0 里程碑改为"创建规则配置占位和语料入口，不生成正式 alias_dictionary"
  - 验证入口改为 `python -m agent_serving.scripts.run_serving`
  - dev mode 入口改为实际实现的入口，mining 入口标注 M2+
- **提交**：`727c6f3` `[claude]: fix P2 — revise architecture baseline M0 milestone and dev mode entry`

### P3: corpus_seed README 把未来命令写成当前可用

- **根因**：`corpus_seed/README.md` 中的 pipeline 命令无阶段标注
- **修复**：添加"以下命令为 M2+ 计划入口，当前 M0 尚未实现"标注
- **提交**：`daaf86d` `[claude]: fix P3 — annotate corpus_seed pipeline command as M2+ planned`

## 验证结果

```
pip install -e ".[dev]" — 成功
pytest agent_serving/tests/ — 2 passed (test_health + test_install_smoke)
python -c "from setuptools import find_packages; print(find_packages(...))" — 26 packages
```

## 回交给 Codex

请复核 P1/P2/P3 修复是否符合审查预期。
