# budui-oss-deploy

把已准备好的静态发布产物安全部署到阿里云 OSS。技能默认使用独立 Bucket、项目语义化的 `budui.fun` 子域名，并记录部署身份，阻止共享 Bucket 覆盖、无关文件上传和未确认的 DNS 改写。

两种访问方式：

- **临时预览**：OSS 默认域名
- **正式发布**：默认生成 `budui.fun` 子域名；个人主页用 `me.budui.fun`，产品使用项目 slug。自定义域名需证书后才启用 HTTPS。

## 功能

- 前端项目：构建后检查实际发布目录和 `index.html`，再上传（不猜 `dist/`）
- 任意静态站：先生成只含运行资源的发布目录，再直传
- 自动设置 Content-Type 与缓存策略（html/js/css 不缓存）
- `--bucket` 显式指定目标桶（优先于环境变量兜底值），运行全程打印目标桶
- `--dry-run` 只读预演：列出将上传/将删除清单，不做任何修改
- 默认拒绝向非空 bucket 根路径上传，避免覆盖同 bucket 的其他站点
- 拒绝 `docs/`、`tests/`、`.git/`、`node_modules/`、锁文件和大文件进入发布包
- 默认不删除云端文件；`--prune` 清理多余旧文件（仅限目标前缀内，删除前先备份到 `_trash/`）
- 配置静态网站托管：index.html 首页 + SPA 404 回退
- 自定义域名：先 OSS 域名绑定（PutCname）、归属验证，成功后才改云解析 CNAME；域名已指向别的 bucket 时在任何修改前中止
- 将 Bucket、区域、域名、发布目录和 HTTPS 状态写入 `tasks/oss-deployment.json`，后续更新沿用同一目标

## 使用

1. 设置环境变量（密钥来自阿里云 RAM 控制台，建议最小权限；用 `--domain` 需额外 `AliyunDNSFullAccess`）：

```
OSS_ACCESS_KEY_ID=...
OSS_ACCESS_KEY_SECRET=...
OSS_BUCKET=my-site
OSS_REGION=oss-cn-hangzhou
```

2. 对 AI 说"把这个项目部署到 OSS / 发布到 app.budui.fun"，或直接运行：

```bash
node scripts/deploy.mjs --source dist --bucket my-site --state-file tasks/oss-deployment.json [--domain app.budui.fun] [--cert-dir ~/certs] [--prefix app] [--prune] [--dry-run] [--no-spa]
```

## 隔离与覆盖保护

- 一个独立站点使用一个 bucket；自定义域名不能与 `--prefix` 组合，因为 OSS 域名绑定始终落到 bucket 根路径。
- 目标桶用 `--bucket` 显式指定；`~/.oss-deploy.env` 里的 `OSS_BUCKET` 只是兜底，属于别的站点时不能借用。
- 若 bucket 根路径已有文件，脚本会停止。只有确认其完全属于本次站点时才使用 `--allow-existing-root`。
- 若目标域名已有指向别的 bucket 的 CNAME，脚本在任何修改前中止，并从 endpoint 反推正确桶名；确认迁移用 `--force`，改写已有 DNS 记录还要 `--replace-domain-dns`。
- 默认不删除云端旧文件；`--prune` 才清理，删除前先备份到 `_trash/<时间戳>/`。清根前缀时若桶还绑着其他域名，需 `--force` 确认。
- 单个文件默认最大 50 MB；确实需要大媒体文件时使用 `--allow-large-files`。若发布目录仍含开发文件，可显式使用 `--allow-project-source`，但它不应成为常规路径。
- 删除有备份和确认，但同名文件覆盖（发新版）不需要额外确认；先 `--dry-run` 可以预览。

## 验证

```bash
node --check scripts/deploy.mjs
```

发布后必须验证 CNAME、首页正文、关键 CSS 与至少一张图片均返回 200 且 Content-Type 正确。无证书的自定义域名只报告 `http://` 地址；配置证书后才报告 `https://`。

## 安装与使用

```bash
npx skills add chuopen/budui-skills --skill budui-oss-deploy
```

可以直接说：

- “把这个静态站部署到 OSS，绑定 `ticket.example.com`，不要影响已有网站。”
- “发布 `dist/` 到一个新的 OSS bucket，并验证 HTTP 200。”

## 排错

- 看到“根路径已有对象”：不要添加放行参数，优先改用新 bucket；只有确认这是同一个站点才使用 `--allow-existing-root`。
- 看到“已有 CNAME”：先确认旧域名页面不再需要，再使用 `--replace-domain-dns`。
- 看到“发布目录不是干净产物”：先建立发布目录，只复制实际运行的 HTML、CSS、JS 和资源文件。

## HTTPS 证书（自定义域名）

阿里云免费证书需控制台领取（每年 20 张免费）：数字证书管理服务 → 免费证书 → 创建 → DNS 验证 → 下载 NGINX 格式，重命名为 `cert.pem` / `key.pem` 放入证书目录，部署时传 `--cert-dir`。每年过期后重新领取并重跑部署即可更新证书。

## 版权

Copyright (c) 不兑 · https://github.com/chuopen/
