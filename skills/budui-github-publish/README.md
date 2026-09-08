# budui-github-publish

把本地项目安全地创建或更新到 GitHub。它会识别当前 GitHub 身份、检查项目是否已有远端和发布记录、要求确认公开/私有、扫描常见发布风险，并在写入后回读验证；Windows 证书链受限时会先自行尝试进程级连通性恢复。

## 直接这样说

```text
上传到 GitHub
帮我上传到 GitHub，建私有仓库
把这个项目更新到 GitHub 上现有的仓库
先检查这个项目以前有没有上传过 GitHub，不要推送
```

你可以直接这样说：

```text
上传到 GitHub
帮我上传到 GitHub，先预检但不要推送
```

## 安装

```bash
npx skills add chuopen/budui-skills --skill budui-github-publish
```

## 行为边界

- 不保存 GitHub Token；使用你当前 `gh` 登录态。
- 没有明确可见性时会问你“公开还是私有”。
- 不会强推、覆盖远端、改可见性或泄露秘密文件。
- 不会因为仓库同名就自动把项目推过去。

## 项目级默认值

如要让某个项目总是默认私有，可在项目根目录创建：

```json
{"visibility":"private"}
```

文件名为 `.budui-github-publish.json`。公开仓库同理使用 `public`；仍会在第一次新建仓库前展示目标和影响。

## 前置条件

- 已安装 Git 和 GitHub CLI (`gh`)
- 已安装 GitHub CLI (`gh`)；Skill 会先验证身份并尝试恢复受限网络下的 CLI 连通性
- 目标项目在本机可读写

## 验证

```bash
python3 scripts/preflight.py .
python3 scripts/verify_remote.py OWNER/REPO main
python3 scripts/secret_gate.py .
```

## Troubleshooting

- `gh` 无法读取身份：预检会自动以进程级备用证书链重试；仍失败时才报告网络阻断，不要求粘贴 Token。
- Git HTTPS 报 `CRYPT_E_REVOCATION_OFFLINE`：仅对失败命令临时加 `-c http.schannelCheckRevoke=false` 重试一次，不写入全局配置。
- 无法判断是否为同一项目：提供明确的 `OWNER/REPO`；不会自动按名称匹配。
- 不知道公开还是私有：先选择私有，或者在项目配置中明确写入 `visibility`。

## 已验证范围

触发边界、目录结构与本地预检脚本由本包验证。对真实 GitHub 仓库的创建/更新需要在具体项目中由用户确认后执行。

借鉴来源：https://github.com/mengto/skills; https://github.com/daymade/claude-code-skills; https://github.com/jezweb/claude-skills
