# 先例调研

- 日期：2026-09-08
- 查询：`OSS static site deployment shared bucket isolation`、`static deployment release artifact allowlist large file guard`。
- 结果：本机缺少 `npx` 所需的可执行环境，统一检索器在启动阶段失败；本次无可引用的外部候选，记为 `missing evidence`。
- 采用的设计：来自本次已验证事故的通用安全规则——非空共享根路径默认拒绝、独立域名使用独立 bucket、发布目录最小化、已有 DNS 记录显式改写。
