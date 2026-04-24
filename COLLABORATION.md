# GitHub 协作开发指南（Branch 模式）

> 本文档面向项目全体成员。管理员看"〇、管理员初始设置"，新成员看"一、初始设置"起。

---

## 项目角色

| 角色 | 职责 | GitHub 权限 |
|------|------|------------|
| 管理员（fzl194） | 审查 PR、合并代码、维护 master 和共享模块 | Owner |
| Mining 负责人 | 开发 `knowledge_mining_v2/` | Write |
| Serving 负责人 | 开发 `agent_serving_v2/` | Write |

## 核心规则

- **master 分支受保护**，任何人都不能直接 push，必须通过 Pull Request（PR）合并
- 每个人只改自己负责的文件夹，不碰别人的代码
- 一个功能一个分支，小批量提 PR

---

## 〇、管理员初始设置（只做一次）

以下操作由管理员在 GitHub 网页上完成，新成员无需操作。

### 1. 邀请协作者

1. 打开仓库页面 → **Settings** → **Collaborators** → **Add people**
2. 输入对方的 GitHub 用户名，选择 **Write** 权限，发送邀请
3. 对方邮箱会收到邀请，点击 Accept 接受
4. 两名成员都邀请完

### 2. 保护 master 分支

1. **Settings** → **Branches** → **Add branch protection rule**
2. Branch name pattern 填 `master`
3. 勾选：
   - **Require a pull request before merging**
   - **Require approvals** → 填 1
4. 点击 **Create**

设置后，任何人（包括管理员自己）都不能直接 push 到 master，必须通过 PR 合并。

### 3. 日常职责

- 收到 PR 通知后，在 PR 页面审查代码（查看 Files changed）
- 有问题就在代码行上留 Comment，要求修改
- 没问题就 Approve，然后点击 **Squash and merge** 合并（保持 master 历史干净）

---

## 一、新成员初始设置（只做一次）

### 1. 接受邀请

管理员会通过 GitHub 邀请你成为协作者。你会收到邮件，点击 Accept。

### 2. 克隆仓库

```bash
git clone git@github.com:fzl194/KnowledgeBase.git
cd KnowledgeBase
```

> 如果用 HTTPS：`git clone https://github.com/fzl194/KnowledgeBase.git`

### 3. 配置你的身份

```bash
git config user.name "你的名字"
git config user.email "你的邮箱"
```

---

## 二、日常开发流程

每次开发一个新功能，重复以下步骤：

### 第 1 步：从最新的 master 建分支

```bash
git checkout master
git pull origin master
git checkout -b 你的模块/功能描述
```

分支命名示例：

```
mining-v2/embedding-generator     ← Mining 负责人
mining-v2/discourse-relation      ← Mining 负责人
serving-v2/vector-retriever       ← Serving 负责人
serving-v2/rrf-fusion             ← Serving 负责人
```

### 第 2 步：写代码

正常开发，在你的文件夹下写代码。

### 第 3 步：提交

```bash
git add 你改的文件路径
git commit -m "类型(模块): 简短描述"
```

提交消息格式：

```
[你的名字]: 简短描述做了什么
```

参考仓库历史提交风格：

```
[mining-v2]: add EmbeddingGenerator operator
[serving-v2]: fix vector similarity calculation
[mining-v2]: extract Segmenter protocol from hardcoded logic
```

用 `[模块名]` 开头，后面跟简洁描述即可。

### 第 4 步：推送到远程

```bash
git push -u origin 你的模块/功能描述
```

第一次推送要带 `-u`，后面直接 `git push` 就行。

### 第 5 步：提 Pull Request

1. 打开 GitHub 仓库页面：https://github.com/fzl194/KnowledgeBase
2. 会出现黄色提示栏，点击 **Compare & pull request**
3. 确认：base 是 `master`，compare 是你的分支
4. 填写标题和描述，说明改了什么、为什么改
5. 点击 **Create pull request**

### 第 6 步：等待审查

管理员会审查你的代码。可能有以下结果：

- **Comment**：有问题，按评论修改后重新 push 到同一分支，PR 自动更新
- **Approve**：审查通过，管理员会合并
- **Request changes**：需要改，改完重新 push

### 第 7 步：合并后同步

管理员合并你的 PR 后，你本地 master 落后了，要同步：

```bash
git checkout master
git pull origin master
```

---

## 三、处理分支冲突

如果你的分支开发期间 master 已经有了新提交，提 PR 时可能有冲突：

```bash
git fetch origin
git rebase origin/master
```

如果有冲突：

1. Git 会停下来，告诉你哪些文件冲突
2. 打开冲突文件，找到 `<<<<<<<` 和 `>>>>>>>` 标记，手动选择保留哪部分
3. 解决后：

```bash
git add 解决了冲突的文件
git rebase --continue
```

4. rebase 完成后强制推送（因为历史变了）：

```bash
git push -f origin 你的模块/功能描述
```

---

## 四、文件夹分工

```
KnowledgeBase/
├── knowledge_mining/          ← 管理员维护，不要改
├── knowledge_mining_v2/       ← Mining 负责人开发
├── agent_serving/             ← 管理员维护，不要改
├── agent_serving_v2/          ← Serving 负责人开发
├── llm_service/               ← 管理员维护，不要改
├── databases/                 ← 共享 schema，改之前和管理员确认
├── shared/                    ← 共享数据类，改之前和管理员确认
├── docs/                      ← 文档，各自可以更新自己模块的部分
├── DELIVERABLES.md            ← 交付件定义，管理员维护
└── COLLABORATION.md           ← 本文件，管理员维护
```

**原则：**
- 只改自己 `xxx_v2/` 文件夹下的代码
- 如果需要改共享部分（`databases/`、`shared/`），在 PR 里说明原因
- 绝对不要改别人负责的文件夹

---

## 五、常见问题

### Q: 我把代码写错了，想撤回上一次 commit？

```bash
git reset HEAD~1              # 撤回 commit，保留文件修改
git reset --hard HEAD~1       # 撤回 commit，丢弃文件修改（慎用）
```

### Q: 我在 master 上误写代码了怎么办？

```bash
# 把修改挪到一个新分支
git checkout -b 你的模块/功能描述
git add .
git commit -m "feat: xxx"
git push -u origin 你的模块/功能描述
# 然后切回 master 并丢弃这些修改
git checkout master
git checkout .                 # 丢弃未提交的修改
```

### Q: push 被拒绝了？

```bash
git pull origin 你的分支名 --rebase
git push origin 你的分支名
```

### Q: 怎么看当前在哪个分支？

```bash
git branch                    # 看本地分支，* 号标记当前分支
git branch -a                 # 看所有分支（包括远程）
```

---

## 六、完整流程图

```
开发新功能：
  master pull ──→ 建分支 ──→ 写代码 ──→ commit ──→ push ──→ 提PR ──→ 等审查
                                                                          │
                                                                    ┌─────┴─────┐
                                                                    │ 要修改？   │
                                                                    │           │
                                                                   是          否（Approve）
                                                                    │           │
                                                               改代码 → push   管理员 Merge
                                                                    │           │
                                                                    └──→ 继续等   pull master → 建新分支 → 继续下一个功能
```
