# 不兑的专属 Skills 仓库

不兑（budui）的个人 Agent 技能合集。

| Skill | 用途 |
|---|---|
| [budui-meta-skill](skills/budui-meta-skill/SKILL.md) | 先确认需求，再创建个人技能；小工具采用轻量流程 |
| [budui-github-publish](skills/budui-github-publish/SKILL.md) | 识别已有仓库、检查敏感信息、创建或更新 GitHub 项目 |

## 安装

```bash
npx skills add chuopen/budui-skills --skill budui-meta-skill
npx skills add chuopen/budui-skills --skill budui-github-publish
```

## 使用

“用不兑元技能，帮我把这个工作流程做成 Skill。”

“帮我上传到 GitHub，公开即可。”

GitHub 发布需要 Git、已登录的 gh 和 gitleaks。扫描目录及历史，不上传 API Key、Token、密码、私钥或用户私密资料。扫描通过不等于绝对无泄漏，发布前仍须审核文件范围。Skill 使用运行时登录态，不包含凭据。

## 来源与许可

元技能基于 [joeseesun/qiaomu-meta-skill](https://github.com/joeseesun/qiaomu-meta-skill) 2.8.1 定制，保留该目录的原始 MIT 许可。发布技能为不兑的定制工作流，参考来源见其 manifest。元技能的原始历史报告、宣传素材不随本合集分发；历史报告相关检查不属于本分发包验证范围。

本合集按技能分目录；仓库根目录不是 Skill 入口。未提供其他作者的个人资料、凭据或本机运行日志。
