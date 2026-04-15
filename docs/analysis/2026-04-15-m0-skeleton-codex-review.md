# M0 Skeleton Codex Review

> 任务：TASK-20260415-cloud-core-architecture
> 审查对象：Claude M0 项目骨架实现
> 审查人：Codex
> 日期：2026-04-15
> 结论：需要修复后再闭环

## 审查背景

Claude 已完成 M0 项目骨架，实现目标是创建最小可运行系统，使 `GET /health` 返回 200。M0 明确不包含数据库 schema、配置体系、挖掘 pipeline、正式 `alias_dictionary` 和业务 API。

本轮审查覆盖 Claude 在 M0 阶段的完整提交链，而不是只看最新 handoff：

- `6750532` `[claude]: M0 T1-T2 — pyproject.toml + directory skeleton`
- `cd19f56` `[claude]: M0 T3 — failing health endpoint test + fix pyproject.toml build`
- `a13b4f6` `[claude]: M0 T4 — FastAPI app with health endpoint, test passes`
- `859e7d6` `[claude]: M0 T5 — serving entry point (run_serving.py)`
- `1e1fc0b` `[claude]: add rule config placeholders and corpus seed (M0 T6)`
- `00ded06` `[claude]: add env template, placeholder scripts and skill (M0 T7)`
- `da9a3f7` `[claude]: M0 handoff to Codex (T9)`
- `46373ff` `[claude]: add Python/pytest artifacts to .gitignore`

## 审查范围

- `pyproject.toml`
- `agent_serving/serving/main.py`
- `agent_serving/serving/api/health.py`
- `agent_serving/scripts/run_serving.py`
- `agent_serving/tests/test_health.py`
- `knowledge_mining/`、`knowledge_assets/`、`agent_serving/`、`skills/`、`scripts/` 目录骨架
- `knowledge_assets/dictionaries/*`
- `knowledge_assets/samples/*`
- `docs/handoffs/2026-04-15-m0-claude-handoff.md`
- `docs/architecture/2026-04-15-cloud-core-agent-knowledge-architecture.md` 中与 M0 直接相关的基线描述

## 发现的问题

### P1：`pyproject.toml` 的 package discovery 实际发现 0 个包

证据：

- `pyproject.toml:19-20` 使用 `[tool.setuptools.packages.find] include = ["agent_serving*", "knowledge_mining*"]`
- 当前目录缺少 `agent_serving/__init__.py`、`agent_serving/scripts/__init__.py`、`knowledge_mining/__init__.py`
- 实测命令：

```text
python -c "from setuptools import find_packages; print(find_packages(include=['agent_serving*','knowledge_mining*']))"
[]
```

影响：

- 当前 `pytest` 和 `python -m agent_serving.scripts.run_serving` 能通过，主要依赖当前仓库根目录在 `sys.path` 中。
- 但按当前 setuptools 配置构建 wheel 或在非源码目录消费安装产物时，`agent_serving` / `knowledge_mining` 很可能不会被打入发行包。
- 这会削弱 M0 的关键交付标准：`pip install -e .` 后服务可作为项目包稳定运行。后续 M1/M2 如果在干净环境或 CI 中验证，可能出现“本地源码目录可运行、安装产物不可用”的分裂。

建议修复：

- 方案 A：补齐顶层包文件：`agent_serving/__init__.py`、`agent_serving/scripts/__init__.py`、`knowledge_mining/__init__.py`，继续使用普通 `find_packages`。
- 方案 B：改用 namespace package discovery，并明确包含 `agent_serving.scripts`、`agent_serving.serving`、`knowledge_mining.mining`。
- 增加一个安装产物级 smoke test：在临时目录外执行 `python -c "import agent_serving.serving.main"` 或构建 wheel 后安装验证。

### P2：架构基线仍残留旧 M0 说明，与已执行计划冲突

证据：

- `docs/architecture/2026-04-15-cloud-core-agent-knowledge-architecture.md:532` 仍要求 M0 补充 `knowledge_assets/dictionaries/alias_dictionary.yaml`，且来源是 `old/ontology/domains/cloud_core_network*.yaml` 和 `old/ontology/lexicon/aliases.yaml`。
- `docs/architecture/2026-04-15-cloud-core-agent-knowledge-architecture.md:533` 仍写验证命令为 `python -m agent_serving.serving.run --dev`。
- `docs/architecture/2026-04-15-cloud-core-agent-knowledge-architecture.md:607-608` 仍写 dev mode 入口为 `agent_serving.serving.run` 和 `knowledge_mining.mining.run`。

影响：

- 这与 M0 设计文档、实现计划、handoff 和最终代码不一致。
- 更关键的是，`old/ontology` 已被明确标记为不可靠，不能作为正式 alias 来源。架构基线中残留旧描述，会在后续 M1/M2 计划生成时重新引入已纠正过的错误方向。

建议修复：

- 在原架构文档内增量修订，不新建 v2/v3 文档。
- 将 M0 里程碑中的 `alias_dictionary.yaml` 初版改为“规则配置占位 + Markdown 语料入口”。
- 将 M0 验证入口改为实际实现的 `python -m agent_serving.scripts.run_serving`。
- 将 §11.1 的 dev mode 入口改成当前计划中的真实入口或明确标注为后续 M1/M2 待实现入口。

### P3：`corpus_seed` README 把未来 pipeline 命令写成当前可用命令

证据：

- `knowledge_assets/samples/corpus_seed/README.md` 写明运行：

```text
python -m knowledge_mining.mining.jobs.run --input knowledge_assets/samples/corpus_seed/
```

- 当前 M0 只创建了 `knowledge_mining/mining/jobs/__init__.py`，没有 `knowledge_mining.mining.jobs.run` 模块。

影响：

- 这不是 M0 health endpoint 的阻塞问题，但用户或后续 Agent 直接照 README 操作会得到 `ModuleNotFoundError`。
- 容易把“未来 M2+ 使用方式”误读为“当前 M0 已支持”。

建议修复：

- 将 README 里的命令标注为“M2+ 计划入口，当前 M0 尚未实现”。
- 或在 M0 补一个只输出“not implemented”的 `run.py` 占位模块，但这会扩大当前骨架范围；更推荐先修正文档表述。

## 测试缺口

- 已有 `agent_serving/tests/test_health.py` 覆盖 ASGI 层 `/health`，测试通过。
- 缺少安装产物级验证，未证明 setuptools discovery 和 wheel 内容正确。
- 缺少从非仓库根目录执行 import / module entrypoint 的 smoke test。
- 未验证 Python 3.11，仅在 Python 3.12.7 环境验证。

## 已执行验证

```text
git status --short
```

执行时只返回 Git 全局 ignore 权限警告，未看到已跟踪文件的未提交差异。

```text
python -m pytest agent_serving\tests\test_health.py -v
```

结果：`1 passed`。测试过程中出现 `.pytest_cache` 写入权限警告，不影响 health 测试结论。

```text
python -m agent_serving.scripts.run_serving --help
```

结果：启动入口参数解析正常。

```text
python -m agent_serving.scripts.run_serving --port 8765
Invoke-RestMethod http://127.0.0.1:8765/health
```

结果：

```json
{"status":"ok","version":"0.1.0"}
```

```text
python -c "from setuptools import find_packages; print(find_packages(include=['agent_serving*','knowledge_mining*']))"
```

结果：`[]`，确认 package discovery 存在问题。

## 回归风险

- 如果后续阶段引入 CI、wheel 构建、容器构建或从非源码目录运行服务，P1 可能直接变成启动失败。
- 如果架构基线不修正，后续任务可能再次把 `old/ontology` 当作 alias seed，污染 Phase 1A 资产边界。
- README 中未来命令未标注阶段，会增加协作误操作概率。

## 建议修复项

1. 修复 package discovery，确保 `find_packages` 或等效 discovery 能发现 `agent_serving`、`agent_serving.scripts`、`agent_serving.serving`、`knowledge_mining`、`knowledge_mining.mining`。
2. 增加安装产物级 smoke test，至少覆盖非仓库根目录下 `import agent_serving.serving.main`。
3. 修订架构文档 M0 里程碑和 dev mode 入口，移除旧 `alias_dictionary.yaml` seed 描述。
4. 将 `corpus_seed/README.md` 中的 pipeline 命令标注为 M2+ 计划入口，避免被当作 M0 可运行能力。

## 无法确认的残余风险

- 未构建 wheel 并检查产物内容；P1 已通过 discovery 结果确认，但具体安装失败形态需在修复后用打包验证闭环。
- 未验证 Linux/macOS。
- 未验证 Python 3.11。

## 管理员介入影响

管理员已确认 Agent / Skill / Serving / Assets / Mining 分层架构。Codex 此前基于管理员补充前提指出 `old/ontology` 不可靠，Claude 已在 M0 计划和最终代码层面采纳；但架构基线局部仍有旧描述残留，需要 Claude 修订。

## 最终评估

M0 的运行态最小功能已经成立：`GET /health` 可返回 200，目录骨架和规则占位总体符合修订后的 M0 计划。

但本轮不能直接判定闭环。`pyproject.toml` 的 package discovery 返回空列表是实质性交付问题，需要修复；架构基线残留旧 alias 来源和旧启动命令也需要同步修正后，M0 才适合进入闭环确认。

## 复核结论（2026-04-15）

Claude 已通过 `docs/handoffs/2026-04-15-m0-claude-fix.md` 回交 P1-P3 修复。复核结果如下：

- P1 已满足 M0 要求：补齐顶层 `__init__.py` 后，`find_packages(include=['agent_serving*','knowledge_mining*'])` 实测返回 27 个包，且从仓库外目录执行 `from agent_serving.serving.main import app` 能正常导入。
- P2 已满足当前架构变化后的 M0 要求：架构基线中的 M0 验证入口已改为 `python -m agent_serving.scripts.run_serving`，挖掘态入口标注为 M2+，不再要求 M0 从 `old/ontology` 生成正式 `alias_dictionary.yaml`。
- P3 已满足 M0 要求：`corpus_seed/README.md` 已明确说明 pipeline 命令是 M2+ 计划入口，当前 M0 尚未实现。

验证备注：

- `python -m pytest agent_serving\tests -v` 在当前机器默认临时目录权限受限时失败于 pytest `tmp_path` fixture 初始化，不是业务代码失败。
- 手工替代验证已覆盖 M0 关键风险：包发现、仓库外导入、health endpoint 既有测试与启动入口。

最终评估更新：M0 修复可接受，按当前项目架构变化无需继续在 M0 阶段追加更重的打包或跨平台验证。后续风险留到 M1/M2 的 CI 或打包任务中处理。
