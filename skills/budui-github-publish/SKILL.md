---
name: budui-github-publish
description: |
  Safely publish or update the user's local project on GitHub. Use when the user says “上传到 GitHub”, “帮我上传到 GitHub”, “推送到 GitHub”, “发布到 GitHub”, “创建 GitHub 仓库”, or asks whether a local project was already uploaded. Detect the authenticated GitHub identity and existing project/repository relationship, determine whether this is an update or a new repository, inspect publish readiness, require an explicit public/private choice when unknown, preview the exact remote change, then create or update the repository and independently verify it. Do not use for generic Git explanations, a one-off git command, GitHub Releases only, or requests that explicitly say not to upload.
metadata:
  version: "0.1.0"
  author: 不兑 (budui)
---

# Budui GitHub Publish

把“上传到 GitHub”变成一次可识别、可审计、可验证的项目发布，而不是盲目 `git push`。

## 固定安全边界

- 只从本机 `gh auth status` 和 `gh api user` 读取当前 GitHub 身份；绝不读取、显示、保存或要求用户粘贴 Token。
- 先检查项目目录、Git 状态、已有 remote、GitHub 仓库与历史记录，再判断“更新现有项目”或“创建新项目”。不因名称相似就写入别的仓库。
- 若仓库可见性没有由用户在当前请求或项目配置明确指定，必须在任何远程写入前询问“公开还是私有”。绝不默认公开。
- 新建仓库、首次推送、改变可见性、覆盖远端、强推、删除分支或仓库都是独立的高影响动作；目标、影响和恢复方式不明确时暂停。
- 发布前必须检查暂存差异、未跟踪文件、`.gitignore`、常见秘密文件、README、许可证及项目可用的构建/测试命令。发现秘密或私密材料时阻断发布。
- 不使用 `git add -A` 向混合目录盲目暂存；仅暂存已审核的项目文件。保留用户无关的脏改动。
- 成功命令不是完成证明。每次创建或推送后都用 GitHub API/CLI 回读仓库、默认分支和提交 SHA。

## 工作流

1. 在目标项目根目录运行 `scripts/preflight.py .`，读取身份、仓库线索、Git 状态与发布风险；先报告，不写入。
2. 判断项目身份，优先级如下：现有 `origin` → `.git` 历史与 GitHub 远端 → 用户明确的 `OWNER/REPO` → 同名仓库搜索结果。多个候选或名称碰撞时，展示候选并让用户选择。
3. 明确交付动作：更新已有仓库，或创建新仓库。新建时确认仓库名、owner、可见性；更新时确认远端与分支。公开/私有未知时只问这一项，不做远程写入。
4. 审核发布范围：展示将提交的文件、忽略项、秘密扫描结果、README/许可证状态和可执行的验证结果。阻断项必须先修复；非阻断项明确列入报告。
5. 在最后一次远程写入前给出简短预览：`目标`、`可见性`、`分支/提交`、`将上传文件`、`影响`、`恢复方式`。用户已在当前会话明确授权目标与可见性时直接执行，不重复确认；仍有实质歧义时才询问。
6. 更新项目时先获取远端，禁止 force push；有分歧或冲突时停止并说明。
7. 创建项目时用 `gh repo create OWNER/REPO --private|--public`；推送使用普通分支推送。不要自动创建 Release、Pages、Issue 或 PR，除非用户另行要求。
8. 用 `scripts/verify_remote.py OWNER/REPO BRANCH` 回读验证，报告“已验证更新 / 已验证创建 / 已满足无需写入 / 阻断”。

## 用户配置与默认值

- 身份：自动使用当前 `gh` 登录账号；若用户明确指定组织或另一个 owner，先验证该 owner 的创建权限。
- 仓库名：优先项目目录名，必要时提出规范化建议，但不静默重命名项目或仓库。
- 可见性：没有明确选择时必须询问；可在目标项目的 `.budui-github-publish.json` 中写入 `{"visibility":"private"}` 或 `{"visibility":"public"}` 作为该项目的持久默认值。
- 更新识别：已有 `origin` 指向 GitHub 时默认视为同一项目；没有 remote 时，只将远端搜索结果作为候选证据，绝不自动认领。

详细判定、发布前标准与恢复方式见 [references/publish-policy.md](references/publish-policy.md)。


## 必须执行的敏感信息检查

- API Key、访问令牌、密码、Cookie、私钥、服务账号 JSON、连接字符串和真实用户资料不得上传，包括私有仓库。
- `.gitignore` 不能移除已跟踪文件或历史中的秘密。审核暂存区实际内容、未跟踪文件、将推送的 Git 历史、LFS 对象、子模块和日志/附件；不要只检查文件名。
- 运行 `python3 scripts/secret_gate.py PROJECT_DIR`；它使用 gitleaks 检查工作目录与全部 Git 历史，失败或工具缺失必须阻断。再人工核对最终 staged diff 和上传范围。检测器不能证明没有所有类型的秘密。
- 检测输出只能展示文件路径、规则编号和位置，必须脱敏，禁止输出秘密原文。扫描报告存放在项目外的临时目录，不要提交报告。
- 命中后排除或改为占位模板；若已进入历史，停止推送并告知需要轮换凭据及处理历史。未经授权不得强推重写历史。
- 仅上传必需文件，默认排除原始聊天记录、私有报告、机器路径、真实环境配置、备份和身份凭据。`.env.example` 只有经内容审核确认全为占位值才可提交。
- 修改文件或暂存内容后重跑检查。上传后比较远端提交 SHA 与预期提交，再检查剩余未提交/未跟踪文件，明确列出有意未上传项，不能宣称绝对无遗漏。


## 不兑专属 Skill 仓库（优先于单技能发布默认值）

用户已指定所有个人 Skill 发布到 `chuopen/budui-skills`，展示名称“不兑的专属 Skills 仓库”，可见性公开。
当用户说“把这个 Skill 上传到 GitHub”时，默认更新该合集的 `skills/<skill-name>/`，不另建单技能仓库；普通业务项目不适用此默认值。
先读取仓库实际状态和目标子目录，保留其他技能；同名且身份不明确时才询问。使用临时 checkout 整合目标目录，经敏感信息扫描后通过分支和 PR 更新，回读合并提交，验证 `npx skills add chuopen/budui-skills --list` 可发现该技能。
单技能 publish_skill.py 不支持合集布局，禁止对该合集直接执行该发布器；采用 Git/gh 的等价分支、PR、检查、合并流程。仅在用户要求版本发布时创建 Release。
不必重复询问本合集的名称和公开选择；若账号、仓库或公开风险与已确认范围发生实质变化再确认。已明确上传的授权允许执行常规提交和推送。
