# 飞书推送规范

四件套生成后默认仅本地交付。用户明确要求“推送飞书”时才执行本页流程。

---

## 1. 前置条件（已在本机验证）

| 项 | 状态 |
|---|---|
| `lark-cli` | 优先 `LARK_CLI_PATH`，再 PATH（Linux/容器），最后回退 Windows workbuddy 路径 |
| app_id | `cli_xxxxxxxxxxxx`（feishu） |
| bot 身份 | ✅ ready |
| user 身份 | ⚠️ refresh token 已过期（不影响推送：**bot 发给用户**这条路是通的） |
| 收件人 open_id | `ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`（`--to self` 自动获取） |

> `doctor` 报 `user_identity: warn` **不必处理**——那只影响"以你的身份发消息"。
> 推送用的是 bot 身份 + 你的 open_id，已实测成功。

---

## 2. 命令

```bash
python "<SKILL_DIR>/scripts/render_push.py" \
  --stats "<工作目录>/reports/stats.json" \
  --files "<工作目录>/<主题>专项简报" \
  --to self
```

| 参数 | 说明 |
|---|---|
| `--stats` | `analyze.py` 产出的 stats.json（用于生成摘要卡） |
| `--files` | 四件套前缀，不含扩展名 |
| `--to` | `self`（自动取 open_id）／`ou_xxx`（指定用户）／`oc_xxx`（群） |
| `--dry-run` | 只预览待发清单，不实际发送 |
| `--no-image` | PNG 也走文件通道 |

---

## 3. 四个必须知道的坑

### 坑 1 · 只接受相对路径

```
--file: cwd-relative local path (absolute paths and .. are rejected)
```

**绝对路径和 `..` 会被 lark-cli 直接拒绝。** 脚本的处理方式是 `subprocess.run(..., cwd=文件所在目录)`，
然后只传文件名——**不要改成传绝对路径**。

### 坑 2 · PNG 必须走图片通道

| 通道 | 结果 |
|---|---|
| `--image` | ✅ 聊天内直接预览长图 |
| `--file` | ⚠️ 变成下载附件，失去"一眼看到"的价值 |

Excel/PDF/HTML 反之——它们**不能**走 `--image`，会报错。

### 坑 3 · 图片通道有 ~10MB 上限

超过 `IMAGE_LIMIT`（脚本设为 9MB，留 1MB 余量）时自动降级为 `--file` 并在输出里标注。
实测四件套 PNG 约 900KB～1MB，**当前不会触发**，但数据量增长后需留意。

### 坑 4 · bot 身份不能列 p2p 会话

```
--types=p2p is only supported with user identity (--as user).
To protect user privacy, bot identity cannot list p2p chats.
```

所以**不要试图用 `+chat-list --types=p2p` 去找会话**。直接用 `--user-id ou_xxx` 发即可，
bot 有对方 open_id 就能发。`--to self` 优先通过 `--dry-run` 探测 `context.user_open_id`；无登录态时才读取 `~/.lark-cli/config.json`。配置存在多个不同 open_id 时必须拒绝并要求显式 `--to ou_xxx`，不得猜测收件人。

---

## 4. 摘要卡结构

推送时先发一条文本摘要，让文件消息有上下文：

```
【车门门把手】周报分析完成
主口径 142 条｜渗透率 万分之 101.1（NX8）
正面 0%｜中性 4.2%｜负面 95.8%

附件 4 份
```

字段来源：
- `meta.topic` / `meta.period_name`
- `m2.n` / `m2.penetration` / `m2.universe_label`
- `m2.positive_rate` / `m2.neutral_rate` / `m2.negative_rate`（三档情感分布，缺正面字段时回退只报负面率）

---

## 5. 退出码

| 码 | 含义 | 处理 |
|---|---|---|
| 0 | 全部成功 | — |
| 4 | 部分失败 | 看输出里 `FAIL` 行，本地文件仍在 |
| 5 | 未找到 lark-cli | 提示 `npx skills add larksuite/cli -g -y` |
| 6 | 未确定收件人 | 检查身份与 open_id |

**推送失败不阻断交付**——四件套已在本地落盘，推送只是加分项。

---

## 6. 排错

| 现象 | 原因 | 处理 |
|---|---|---|
| `文件不存在` | 文件名前缀不对 | 四件套命名不统一（Excel 带 `_明细`），脚本会自动试三种命名 |
| `invalid_argument` + p2p | 用 bot 列 p2p 会话 | 别列，直接 `--user-id` 发 |
| 文件消息发出但打不开 | 传了绝对路径 | 保持脚本的 `cwd` 相对路径写法 |
| `refresh token expired` | user 身份过期 | **不用管**，推送走 bot 身份 |
| 提示有新版本 | cli 1.0.94 → 1.0.96 | 可选执行 `lark-cli update`，不影响功能 |

---

## 7. 安全边界

- **只发给自己**（`--to self`）。改成群发或转发他人前必须明确确认。
- **不发敏感数据到外部**——推送目标固定为当前登录用户的 open_id。
- 这是 `write` 级操作；每次外发均以当前用户的明确请求或可撤销的个人偏好为准，历史授权不能跨用户或跨环境继承。

Copyright (c) 不兑 — https://github.com/chuopen/
