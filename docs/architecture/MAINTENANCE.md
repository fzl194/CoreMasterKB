# CoreMasterKB 架构演示文档维护指南

> 文档位置：`docs/architecture/coremasterkb-v1.2-architecture.html`
> 首次创建：2026-04-23
> 维护策略：模块级增量更新

## 文档结构

HTML 演示页包含 11 个独立 Section，每个 Section 可独立更新而不影响其他部分。

| Section | ID | 内容 | 主要数据来源 |
|---------|----|------|-------------|
| 1. 为什么需要知识后端 | `#why` | 背景与定位 | 稳定，很少变化 |
| 2. 设计哲学 | `#philosophy` | 设计决策表 | 新增设计范式时更新 |
| 3. 整体系统架构 | `#architecture` | 五层全景图 + 读写矩阵 | 子系统变化时更新 |
| 4. 数据旅程 | `#journey` | 真实文档追踪（核心叙事） | Pipeline 变化时更新 |
| 5. 数据模型 | `#schema` | 三域 20 表中文说明 | Schema 变更时更新 |
| 6. Mining Pipeline | `#pipeline` | 技术参考 + v1.2 增强 | 阶段逻辑变化时更新 |
| 7. Serving 检索链 | `#serving` | 混合检索架构 + 真实追踪 | 检索策略变化时更新 |
| 8. LLM Service | `#llm` | 能力 + API + 代码示例 | LLM 服务接口变化时更新 |
| 9. Build/Release 生命周期 | `#lifecycle` | 四层抽象 + 状态机 + 场景 | 生命周期逻辑变化时更新 |
| 10. v1.2 目标态 | `#v12` | 五大创新（知识自主演化） | 思想演进时更新 |
| 11. 当前 vs 目标对比 | `#compare` | 12 维度对比表 + 进度 | 任何模块交付时更新 |

## 更新触发条件

### 必须更新的场景

1. **Schema 变更**（加表、改列、改约束）→ 更新 Section 5 + Section 4
2. **Pipeline 阶段变化**（新增/删除/重命名阶段）→ 更新 Section 4 + Section 6
3. **新检索策略上线**（如 Embedding 检索实现）→ 更新 Section 7 + Section 11
4. **LLM Service 接口变化**（新端点、新能力）→ 更新 Section 8
5. **模块交付完成**（v1.2 任何能力从"规划中"变为"已完成"）→ 更新 Section 11
6. **设计思想演进**（新的架构决策、范式调整）→ 更新 Section 2 + Section 10

### 建议更新周期

- **Section 11（对比表）**：每两周或每次交付后更新
- **Section 10（目标态）**：每月或设计评审后更新
- **Section 4（数据旅程）**：Pipeline 重大重构后更新
- **其他 Section**：对应模块变化时按需更新

## 更新方法

### HTML 文件结构

```
HTML 文件按 Section 组织，每个 Section 以注释标记：
<!-- ═══ SECTION N: 标题 ═══ -->
<section class="sec" id="xxx">
  ...
</section>
```

### 更新步骤

1. **定位 Section**：在 HTML 中搜索对应的 `<!-- ═══ SECTION` 注释
2. **读取最新数据**：从对应源文件收集上下文（见下方数据源映射）
3. **替换 Section 内容**：保留 `<section>` 标签和 id，更新内部内容
4. **验证**：浏览器打开确认渲染正确
5. **提交**：commit message 格式 `[claude]: update architecture section N - <原因>`

### 数据源映射

| 需要更新的内容 | 应读取的源文件 |
|---------------|---------------|
| Schema 信息 | `databases/*/schemas/*.sqlite.sql` |
| Pipeline 阶段 | `knowledge_mining/` 下的 Pipeline 代码 + `knowledge_mining/README.md` |
| 检索策略 | `agent_serving/serving/retrieval/` 下的代码 |
| LLM 服务 | `llm_service/README.md` + `llm_service/QUICKSTART.md` |
| 架构设计思想 | `docs/architecture/*.md` + `old/Self_Knowledge_Evolve/` |
| v1.2 演进项 | `.dev/2026-04-22-v12-evolution-backlog.md` |
| 实现进度 | 各模块测试通过状态 + `COLLAB_TASKS.md` |

## 版本记录

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-04-23 | v2.0 | 完整重写：11 个 Section，真实文档追踪，知识自主演化五大创新 |
| 2026-04-22 | v1.0 | 初始版本（已废弃：暗色主题 slideshow 格式） |

## 注意事项

- HTML 是单文件自包含（CSS 内联），无外部依赖，可直接浏览器打开
- Section 4（数据旅程）和 Section 7（检索链）使用同一份真实文档，保持一致性
- Section 11（对比表）的进度标记必须与实际交付状态同步，不要虚标
- 目标态（Section 10）不引述外部来源，所有创新作为自主设计呈现
- 数据旅程的追踪文档可以替换：选择当前知识库中最丰富、最具代表性的文档
