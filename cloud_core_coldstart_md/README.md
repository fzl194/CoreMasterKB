# 云核心网冷启动 Markdown 样本包

这是一个用于 Graph-RAG / Agent Knowledge Backend 冷启动的数据样本包，按多种文档视图组织，便于你直接喂给现有 pipeline 做第一阶段导入、切分、索引和检索验证。

## 目录结构

- `00_reference_from_user/`：保留你提供的两个示例文档，作为格式参考。
- `01_features/`：特性概述类文档。
- `02_commands/`：命令参考类文档。
- `03_procedures/`：配置流程类文档。
- `04_troubleshooting/`：故障排障类文档。
- `05_constraints_alarms/`：约束、告警、检查清单类文档。
- `manifest.jsonl`：样本元数据清单。
- `stats.json`：数量统计。

## 设计目的

这批样本不是为了追求“完全仿真官方手册”，而是为了在冷启动阶段优先覆盖高价值问法：

- 查命令
- 查参数
- 查配置流程
- 查前置条件
- 查故障处理
- 查告警与约束

## 建议用法

1. 先把 `source_type=synthetic_coldstart` 和 `source_type=user_reference` 分开入库。
2. 切分时保留标题、二级标题、表格样式数组文本。
3. 对 `doc_type` 建立轻量视图索引：
   - feature
   - command
   - procedure
   - troubleshooting
   - alarm / constraint / checklist
4. 后续有真实厂家文档后，可继续共存，但检索时把真实文档优先级设置高于 synthetic 样本。

## 数据属性

- 本样本包中，`00_reference_from_user/` 为用户提供示例。
- 其余文档为按云核心网场景批量构造的冷启动样本。
- 这些样本适合做 pipeline、Graph-RAG、Skill 工具链联调，不应替代正式厂家手册作为权威依据。
