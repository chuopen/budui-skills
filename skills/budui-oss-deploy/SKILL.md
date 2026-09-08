---
name: budui-oss-deploy
description: |
  将本地项目部署到阿里云 OSS 静态网站托管。支持两种访问方式：OSS 默认域名（<bucket>.<region>.aliyuncs.com，HTTP，无需备案）和自定义域名（如 xxx.budui.fun，自动 CNAME + 归属验证 + 域名绑定，可加 SSL 证书开 HTTPS；大陆区域要求域名已 ICP 备案）。适用于：前端项目"构建+上传 dist/"、任意静态目录直传、SPA 404 回退。当用户说"部署到 OSS"、"上传到阿里云 OSS"、"发布静态网站"时使用。不适用于：CDN 加速、后端服务部署、OSS 数据迁移或管理类操作。
metadata:
  author: 不兑 (budui)
  version: "0.5.0"
  copyright: "Copyright (c) 不兑"
  homepage: https://github.com/chuopen/
---

# Budui OSS Deploy

把静态项目一键部署到阿里云 OSS。默认域名零门槛；自定义域名全自动（DNS + 归属验证 + 绑定 + 可选证书）。

## 首次使用引导（用户从没碰过阿里云时，按此顺序带用户做）

1. **区分两个概念讲给用户**：OSS = 存网站的仓库（要付费，但静态站约几分钱/月）；RAM = 阿里云的"子账号权限系统"，只是用来生成一把能让脚本开门的钥匙，不额外收费。
2. **创建 AccessKey**（用户必须在控制台做，给具体路径，别只说策略名）：
   - 打开 https://ram.console.aliyun.com/users → 创建用户 `budui-deploy`
   - ⚠️ 新版界面：勾选「**使用永久 AccessKey 访问**」（没有"OpenAPI 调用访问"这个旧叫法了），不勾控制台访问
   - 创建后立刻复制 AccessKey ID 和 Secret（Secret 只显示一次）
   - **授权**：用户列表点进 `budui-deploy`（注意不是"角色"页面）→ 权限管理 → 新增授权 → 同时勾选 `AliyunOSSFullAccess` 和 `AliyunDNSFullAccess`（用自定义域名时 DNS 那个必需）
3. **写凭证文件**：让用户把密钥写进 `~/.oss-deploy.env`（脚本会自动读；密钥永不贴进对话、不进仓库）：

```
OSS_ACCESS_KEY_ID=...
OSS_ACCESS_KEY_SECRET=...
OSS_BUCKET=<全局唯一小写名>
OSS_REGION=oss-cn-hangzhou
```

4. **自定义域名前先查备案**：到 https://beian.miit.gov.cn 信息查询输入根域名。**未备案 + 大陆区域 = 绑定必失败**（报 NoSuchCnameInRecord）。未备案时的选择：走 ICP 备案（约 1-2 周，需购云服务器）或改用香港区域 `oss-cn-hongkong`（免备案，实测可行，大陆访问稍慢）。换区域注意：bucket 名全局唯一，需同时换 `OSS_BUCKET`（如加 `-hk` 后缀），脚本会自动建新 bucket 并把 CNAME 改指向新地址。

## 实测证据（validated，2026-09-08）

- 默认域名部署：HTTP 200（杭州 + 香港区域均验证）
- 自定义域名免备案路线：香港区域 CNAME + TXT 归属验证 + PutCname 全自动成功，`http://job.budui.fun` 200
- CNAME/TXT 跨区域迁移：脚本自动把已有记录**更新**到新地址，无需手动清理
- 限制：未绑证书时 `https://<自定义域名>` 返回 OSS 默认证书（域名不匹配），浏览器告警——属预期，绑证书前一律给用户 http 地址

## 工作流

1. 读 `~/.oss-deploy.env` 或环境变量，缺哪个列哪个并指引用户补。
2. 判断部署模式：有 `package.json` + `build` 脚本 → 先构建（产物目录看 vite/next 配置确认，别猜）；纯静态项目也必须建立只包含 `index.html` 与实际资源的发布目录。禁止把项目根目录直接当发布目录。
3. 运行：

```bash
node "<本skill目录>/scripts/deploy.mjs" --source <发布目录> [--domain <子域名>] [--cert-dir <证书目录>] [--prefix <云端子目录>] [--no-spa]
```

脚本自动完成：发布目录卫生检查 → 创建 bucket（公共读，自动关闭账号级和 bucket 级"阻止公共访问"）→ 上传（正确 Content-Type + 缓存策略）→ 清理前缀内旧文件 → 静态网站托管（index + SPA 404 回退）→ 自定义域名（CNAME → TXT 归属验证（自动等待 90 秒）→ PutCname 绑定）。

4. 部署后验证：curl 首页返回 200 才算成功；自定义域名 DNS 生效需几分钟。
5. 向用户报告访问地址。用了自定义域名提醒：HTTPS 需要证书（见下）。

## 已知坑（实战踩过，脚本已内置对策）

| 坑 | 对策 |
| --- | --- |
| 新版 RAM 界面没有"OpenAPI 调用访问" | 实为「使用永久 AccessKey 访问」 |
| 授权授到了"角色"页面 | 必须在「用户」→ 具体用户 → 权限管理里授 |
| 2024 后新账号默认开启「阻止公共访问」 | 脚本自动关两级并重设公共读 |
| PutCname 报 `BucketAlreadyExists` | 请求格式错了：正确为 POST + `<BucketCnameConfiguration><Cname><Domain>` |
| PutCname 报 `NeedVerifyDomainOwnership` | 脚本自动 CreateCnameToken + 加 TXT + 等待重试 |
| PutCname 报 `NoSuchCnameInRecord` | 域名未备案（或备案无效），查 beian.miit.gov.cn；不愿备案改香港区域 |
| DNS API 报 `MissingRR` | alidns SDK 字段名是 `RR` 大写，type/value 小写 |
| Git Bash 下 `/tmp` 路径变成 `D:\tmp` 或 8.3 短路径 | staging 目录用 Windows 原生绝对路径，脚本内部已用 realpath + 相对路径算 key |
| alidns SDK v3 `Alidns is not a constructor` / `request.validate is not a function` | 用 createRequire 取 `.default`，请求必须用模型类实例化 |
| `ali-oss` 无 PutCname/CreateCnameToken API | 脚本内置 OSS V1 签名（node:crypto）直接调 |

## 证书（HTTPS，自定义域名时）

阿里云免费证书无法可靠 API 签发，走控制台（每年一次，约 10 分钟）：

1. https://yundun.console.aliyun.com/?p=cas → 左侧「免费证书」→ 立即购买（数量 20，¥0）
2. 创建证书 → 类型 RSA、绑定域名填子域名（如 `job.budui.fun`）
3. 验证方式选「**DNS 自动验证**」（DNS 在阿里云时自动加记录），等「已签发」
4. 下载 **NGINX** 格式 → 改名 `cert.pem` / `key.pem` 放入证书目录 → 部署加 `--cert-dir <目录>`
5. 重跑后严格校验 `curl https://<域名>` 返回 200 才算 HTTPS 生效；过期后重新领取重跑即可

## 安全边界

- 密钥只从环境变量或 `~/.oss-deploy.env` 读取；不进代码、仓库、对话。
- 证书私钥只放用户本地目录。
- 默认拒绝向非空 bucket 根路径部署；这可能覆盖同 bucket 的其他域名。独立站点必须使用独立 bucket，只有确认根路径完全属于当前站点时才允许 `--allow-existing-root`。
- `--prefix` 只隔离对象路径，不能隔离自定义域名；带 `--domain` 的独立站点必须用独立 bucket。
- 发布源必须是干净产物目录；默认拒绝 `.git`、`docs`、`tests`、`tasks`、`node_modules`、锁文件及超过 50 MB 的文件。例外必须显式传 `--allow-project-source` 或 `--allow-large-files`。
- 默认不改写已有 CNAME；确认域名切换后才传 `--replace-domain-dns`。
- `--no-clean` 只停止删除旧文件，不能阻止同名文件被覆盖。

## 故障排查（错误码 → 用户动作）

| 现象 | 用户动作 |
| --- | --- |
| `AccessDenied` / `Forbidden.RAM` 403 | RAM 授权没生效：回用户（不是角色）页检查两个策略；新建授权需 1 分钟生效 |
| `NoSuchBucket` | bucket 名或 region 写错 |
| 首页 404 NoSuchKey | 产物目录没有 index.html，检查构建 |
| `NoSuchCnameInRecord` | 域名未备案 → 备案或换香港区域 |
| 域名打不开 | `nslookup -type=CNAME <域名> 8.8.8.8` 查解析，几分钟后再试 |
| PutBucket 被拒 | 脚本会自动关"阻止公共访问"；仍失败去控制台手动关 |
| 依赖安装失败 | `cd scripts && npm install` |
