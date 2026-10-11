# 不兑的专属 Skills 仓库

不兑（budui）的个人 Agent 技能合集。

| Skill | 用途 |
|---|---|
| [budui-meta-skill](skills/budui-meta-skill/SKILL.md) | 将重复工作整理为可验证、可发布的个人 Skill |
| [budui-github-publish](skills/budui-github-publish/SKILL.md) | 审核并安全创建或更新 GitHub 项目，含连通性恢复与远端回读 |
| [budui-oss-deploy](skills/budui-oss-deploy/SKILL.md) | 部署静态站到 OSS，管理独立 Bucket、自定义域名与部署状态 |
| [budui-伙食补贴发票报销](skills/budui-伙食补贴发票报销/SKILL.md) | 节假日伙食补贴发票 PDF → 报销明细 Excel + 每人汇总表 + 问题报告 |
| [budui-dongfeng-nissan-sentiment](skills/budui-dongfeng-nissan-sentiment/SKILL.md) | 东风日产公域舆情监控与结构化数据采集（多平台公开讨论搜索提取） |
| [budui-voc-brief](skills/budui-voc-brief/SKILL.md) | 批量 VOC 数据专项分析与简报生成（正/中/负全貌） |
| [budui-voc-daily](skills/budui-voc-daily/SKILL.md) | VOC 新车日报生成（与周报共用去重口径） |
| [budui-voc-definer](skills/budui-voc-definer/SKILL.md) | VOC 分类标准二三四级「定义/典型内容/不包含」的补写与评审 |
| [budui-voc-weekly](skills/budui-voc-weekly/SKILL.md) | VOC 新车周报生成（HTML 简报 + PNG 长图 + 溯源 Excel，自动环比） |

## 安装

```bash
npx skills add chuopen/budui-skills --skill budui-meta-skill
npx skills add chuopen/budui-skills --skill budui-github-publish
npx skills add chuopen/budui-skills --skill budui-oss-deploy
npx skills add chuopen/budui-skills --skill budui-伙食补贴发票报销
npx skills add chuopen/budui-skills --skill budui-dongfeng-nissan-sentiment
npx skills add chuopen/budui-skills --skill budui-voc-brief
npx skills add chuopen/budui-skills --skill budui-voc-daily
npx skills add chuopen/budui-skills --skill budui-voc-definer
npx skills add chuopen/budui-skills --skill budui-voc-weekly
```

## 使用

“用不兑元技能，帮我把这个工作流程做成 Skill。”

“帮我上传到 GitHub，公开即可。”

“把这个静态站部署到 OSS，绑定 `me.budui.fun`。”

GitHub 发布需要 Git、GitHub CLI (`gh`) 和 gitleaks。Skill 先验证 CLI 身份，并在 Windows 证书链受限时尝试进程级恢复；不保存 Token。扫描目录及历史，不上传 API Key、Token、密码、私钥或用户私密资料。扫描通过不等于绝对无泄漏，发布前仍须审核文件范围。

## 来源与许可

元技能基于 [joeseesun/qiaomu-meta-skill](https://github.com/joeseesun/qiaomu-meta-skill) 2.8.1 定制，保留该目录的原始 MIT 许可。发布技能为不兑的定制工作流，参考来源见其 manifest。元技能的原始历史报告、宣传素材不随本合集分发；历史报告相关检查不属于本分发包验证范围。

本合集按技能分目录；仓库根目录不是 Skill 入口。未提供其他作者的个人资料、凭据或本机运行日志。
