# budui-oss-deploy

把本地项目一键部署到阿里云 OSS 静态网站托管。两种访问方式：

- **默认域名**：`http://<bucket>.<region>.aliyuncs.com`（零配置，HTTP）
- **自定义域名**：如 `https://app.budui.fun`（已备案域名，自动 CNAME + 绑定 + SSL 证书，HTTPS）

## 功能

- 前端项目：自动 `npm run build` 后上传 `dist/`（构建由 AI 会话执行，脚本负责上传）
- 任意静态目录：直传，跳过构建
- 自动设置 Content-Type 与缓存策略（html/js/css 不缓存）
- 清理云端多余旧文件（仅限目标前缀内）
- 配置静态网站托管：index.html 首页 + SPA 404 回退
- 自定义域名：自动添加/更新云解析 CNAME、OSS 域名绑定（PutCname）、可选绑定 SSL 证书

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
node scripts/deploy.mjs --source dist [--domain app.budui.fun] [--cert-dir ~/certs] [--prefix app] [--no-spa] [--no-clean]
```

## HTTPS 证书（自定义域名）

阿里云免费证书需控制台领取（每年 20 张免费）：数字证书管理服务 → 免费证书 → 创建 → DNS 验证 → 下载 NGINX 格式，重命名为 `cert.pem` / `key.pem` 放入证书目录，部署时传 `--cert-dir`。每年过期后重新领取并重跑部署即可更新证书。

## 版权

Copyright (c) 不兑 · https://github.com/chuopen/
