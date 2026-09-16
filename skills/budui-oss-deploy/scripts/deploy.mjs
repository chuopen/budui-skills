#!/usr/bin/env node
/**
 * budui-oss-deploy: 上传静态目录到阿里云 OSS，配置静态网站托管；
 * 可选绑定自定义域名（CNAME + OSS PutCname，可带 SSL 证书）。
 * 密钥只从环境变量读取：OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET / OSS_BUCKET / OSS_REGION
 *
 * v0.7.0 安全模型（2026-09-14 me.budui.fun 误清 job.budui.fun 事故复审后引入）：
 * 1. 目标桶显式化：--bucket > OSS_BUCKET 环境变量 > ~/.oss-deploy.env 兜底，全程打印目标桶
 * 2. 删除是显式行为：默认只上传不删；清理云端多余旧文件必须加 --prune
 * 3. --prune 删除前进回收站：被删 key 先 CopyObject 到 _trash/<时间戳>/ 再删
 * 4. 域名归属前置校验：--domain 的现有 CNAME 指向别的桶时，任何写操作之前中止，
 *    并从 endpoint 反推桶名给出建议（防"发错桶还改走 DNS"）
 * 5. 先绑定后改 DNS：PutCname 成功后才动 CNAME 记录，绑定失败 DNS 保持原样
 * 6. 多站点桶保护：--prune 清根前缀时，若桶还绑着 --domain 以外的域名，要求 --force
 * 7. --dry-run 只读预演：打印将上传/将删除清单，不做任何修改
 */
import { parseArgs } from "node:util";
import { readdir, stat, readFile, realpath, mkdir, writeFile } from "node:fs/promises";
import { join, relative, extname, dirname } from "node:path";
import { createHmac } from "node:crypto";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";

const require = createRequire(import.meta.url);

/** 从 ~/.oss-deploy.env 加载 KEY=VALUE（用户手工创建，密钥不进仓库；已设置的环境变量优先） */
async function loadEnvFile() {
  const envPath = join(process.env.USERPROFILE || process.env.HOME || ".", ".oss-deploy.env");
  try {
    for (const line of (await readFile(envPath, "utf8")).split(/\r?\n/)) {
      const m = line.match(/^\s*(OSS_[A-Z_]+)\s*=\s*(.+?)\s*$/);
      if (m && !process.env[m[1]]) process.env[m[1]] = m[2];
    }
  } catch { /* 文件不存在则忽略 */ }
}

async function loadOss() {
  try {
    return (await import("ali-oss")).default;
  } catch {
    console.log("未找到依赖，正在安装到脚本目录…");
    const r = spawnSync("npm", ["install", "--no-audit", "--no-fund"], {
      cwd: import.meta.dirname,
      stdio: "inherit",
      shell: process.platform === "win32",
    });
    if (r.status !== 0) throw new Error("依赖安装失败，请手动执行: cd scripts && npm install");
    return (await import("ali-oss")).default;
  }
}

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
  ".webp": "image/webp", ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2",
  ".ttf": "font/ttf", ".map": "application/json", ".txt": "text/plain; charset=utf-8",
  ".xml": "application/xml", ".pdf": "application/pdf", ".mp4": "video/mp4", ".webm": "video/webm",
};

const DEVELOPMENT_DIRS = new Set([".git", ".vercel", "node_modules", "docs", "test", "tests", "tasks"]);
const DEVELOPMENT_FILES = new Set(["agents.md", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"]);

async function walk(dir, base) {
  const out = [];
  for (const name of await readdir(dir)) {
    const full = join(dir, name);
    if ((await stat(full)).isDirectory()) out.push(...await walk(full, base));
    else {
      const fileStat = await stat(full);
      out.push({ local: full, key: relative(base, full).split(/[\\/]/).join("/"), size: fileStat.size }); // key 只用相对路径
    }
  }
  return out;
}

function findReleaseHazards(files, maxFileSizeBytes) {
  const development = [];
  const large = [];
  for (const file of files) {
    const parts = file.key.toLowerCase().split("/");
    if (parts.some((part) => DEVELOPMENT_DIRS.has(part)) || DEVELOPMENT_FILES.has(parts.at(-1))) {
      development.push(`${file.key}（开发/管理文件）`);
    }
    if (file.size > maxFileSizeBytes) {
      large.push(`${file.key}（${Math.ceil(file.size / 1024 / 1024)} MB，超过单文件限制）`);
    }
  }
  return { development, large };
}

async function listObjectNames(client, prefix) {
  let marker;
  const remote = [];
  do {
    const list = await client.list({ prefix, "max-keys": 1000, marker }, true);
    remote.push(...(list.objects || []).map((o) => o.name));
    marker = list.nextMarker;
  } while (marker);
  return remote;
}

/** OSS raw HTTP + V1 签名（ali-oss SDK 未覆盖的管控 API；bucket 为空表示账号级） */
async function signedOss(env, method, query, body = "", contentType = "application/xml", noBucket = false) {
  const date = new Date().toUTCString();
  const host = noBucket ? `${env.region}.aliyuncs.com` : `${env.bucket}.${env.region}.aliyuncs.com`;
  const resource = `/${noBucket ? "" : env.bucket}/?${query}`;
  const stringToSign = [method, "", body ? contentType : "", date, resource].join("\n");
  const signature = createHmac("sha1", env.accessKeySecret).update(stringToSign).digest("base64");
  const res = await fetch(`https://${host}/?${query}`, {
    method,
    headers: {
      ...(body ? { "Content-Type": contentType } : {}),
      Date: date,
      Authorization: `OSS ${env.accessKeyId}:${signature}`,
    },
    body: body || undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`OSS ${method} ?${query} 失败 (HTTP ${res.status}): ${text.slice(0, 300)}`);
  return text;
}

/** OSS PutCname（POST /?cname&comp=add，绑定自定义域名；带证书时 cert/key 为 PEM 字符串） */
async function putCname(env, domain, cert, key) {
  const certCfg = cert
    ? `<CertificateConfiguration><Certificate>${cert.replace(/\n/g, "&#10;")}</Certificate><PrivateKey>${key.replace(/\n/g, "&#10;")}</PrivateKey><Force>true</Force></CertificateConfiguration>`
    : "";
  await signedOss(env, "POST", "cname&comp=add",
    `<?xml version="1.0" encoding="UTF-8"?><BucketCnameConfiguration><Cname><Domain>${domain}</Domain>${certCfg}</Cname></BucketCnameConfiguration>`);
}

/** OSS CreateCnameToken（域名归属验证 Token，72 小时有效） */
async function createCnameToken(env, domain) {
  const xml = await signedOss(env, "POST", "cname&comp=token",
    `<?xml version="1.0" encoding="UTF-8"?><BucketCnameConfiguration><Cname><Domain>${domain}</Domain></Cname></BucketCnameConfiguration>`);
  return { token: xml.match(/<Token>([^<]+)<\/Token>/)?.[1] };
}

/** OSS GetCname：列出桶上已绑定的自定义域名（多站点桶检测用） */
async function listBucketCnames(env) {
  try {
    const xml = await signedOss(env, "GET", "cname");
    return [...xml.matchAll(/<Domain>([^<]+)<\/Domain>/g)].map((m) => m[1]);
  } catch { /* 无权限或无绑定：按空处理，不阻断 */ return []; }
}

/** 查询域名当前 CNAME 记录值（域名归属前置校验用），查不到返回 [] */
async function currentCnameValues({ accessKeyId, accessKeySecret }, domain) {
  const D = require("@alicloud/alidns20150109");
  const { Config } = require("@alicloud/openapi-client");
  const client = new D.default(new Config({ accessKeyId, accessKeySecret, endpoint: "alidns.aliyuncs.com" }));
  const existing = await client.describeSubDomainRecords(
    new D.DescribeSubDomainRecordsRequest({ subDomain: domain, type: "CNAME", pageSize: 20 })
  );
  return (existing.body?.domainRecords?.record || []).map((r) => r.value);
}

/** 域名归属前置校验：--domain 现有 CNAME 指向别的桶时中止（在任何写操作之前调用） */
async function guardDomainOwnership(env, domain, force, dry) {
  const mine = `${env.bucket}.${env.region}.aliyuncs.com`;
  let values;
  try {
    values = await currentCnameValues(env, domain);
  } catch (e) {
    console.warn(`  ⚠ 无法查询 ${domain} 的 DNS 记录（跳过归属校验；后续 --replace-domain-dns 保护仍在）: ${e.message}`);
    return;
  }
  const foreign = values.filter((v) => v !== mine);
  if (!foreign.length) return;
  const other = foreign.find((v) => /^[\w-]+\.oss-[\w-]+\.aliyuncs\.com$/i.test(v));
  console.error(`\n中止：${domain} 的 CNAME 当前指向 ${foreign.join("、")}，不是本次目标桶 ${env.bucket}。`);
  if (other) {
    const otherBucket = other.split(".")[0];
    console.error(`该 endpoint 属于桶 ${otherBucket} —— 若这才是正确目标，重跑加 --bucket ${otherBucket}。`);
  }
  console.error(`确认要把 ${domain} 迁移到 ${env.bucket} 的话，加 --force 重跑（DNS 改写仍需 --replace-domain-dns）。${dry ? "（--dry-run 未做任何修改）" : "未做任何修改。"}`);
  process.exit(1);
}

/** 在阿里云 DNS 添加/更新记录（type: CNAME/TXT），返回是否新添加 */
async function ensureDnsRecord({ accessKeyId, accessKeySecret }, domain, type, value, allowReplace = false) {
  const D = require("@alicloud/alidns20150109");
  const { Config } = require("@alicloud/openapi-client");
  const client = new D.default(new Config({ accessKeyId, accessKeySecret, endpoint: "alidns.aliyuncs.com" }));
  const parts = domain.split(".");
  const rr = parts.length > 2 ? parts.slice(0, -2).join(".") : "@";
  const root = parts.slice(-2).join(".");

  const existing = await client.describeSubDomainRecords(
    new D.DescribeSubDomainRecordsRequest({ subDomain: domain, type, pageSize: 20 })
  );
  const records = existing.body?.domainRecords?.record || [];
  if (records.some((r) => r.value === value)) return false;
  if (records.length) {
    if (!allowReplace) {
      throw new Error(`${domain} 已有 ${type} 记录指向 ${records[0].value}；拒绝自动改写。确认切换后加 --replace-domain-dns。`);
    }
    await client.updateDomainRecord(
      new D.UpdateDomainRecordRequest({ recordId: records[0].recordId, RR: rr, type, value })
    );
    console.log(`  ✓ ${type} 已更新: ${domain} → ${value}（原 ${records[0].value}）`);
    return true;
  }
  await client.addDomainRecord(
    new D.AddDomainRecordRequest({ domainName: root, RR: rr, type, value })
  );
  console.log(`  ✓ ${type} 已添加: ${domain} → ${value}`);
  return true;
}

async function main() {
  await loadEnvFile();
  const { values } = parseArgs({
    options: {
      source: { type: "string", short: "s" },
      prefix: { type: "string", short: "p", default: "" },
      bucket: { type: "string", short: "b" },
      domain: { type: "string", short: "d" },
      "cert-dir": { type: "string" },
      "no-spa": { type: "boolean", default: false },
      prune: { type: "boolean", default: false },
      force: { type: "boolean", default: false },
      "dry-run": { type: "boolean", default: false },
      "allow-existing-root": { type: "boolean", default: false },
      "allow-project-source": { type: "boolean", default: false },
      "allow-large-files": { type: "boolean", default: false },
      "max-file-size-mb": { type: "string", default: "50" },
      "replace-domain-dns": { type: "boolean", default: false },
      "state-file": { type: "string" },
      "no-clean": { type: "boolean", default: false }, // 已废弃：v0.7.0 起默认就不删除，仅为兼容保留
    },
  });
  const env = {
    accessKeyId: process.env.OSS_ACCESS_KEY_ID,
    accessKeySecret: process.env.OSS_ACCESS_KEY_SECRET,
    bucket: values.bucket || process.env.OSS_BUCKET,
    region: process.env.OSS_REGION,
  };
  const missing = Object.entries(env).filter(([, v]) => !v).map(([k]) => `OSS_${k.replace(/[A-Z]/g, (c) => "_" + c).toUpperCase()}`);
  if (missing.length) {
    console.error(`缺少环境变量: ${missing.join(", ")}\n请设置后重试（密钥来自阿里云 RAM 控制台，不要写入文件）。`);
    process.exit(1);
  }
  if (values["no-clean"] && !values.prune) {
    console.log("提示: --no-clean 已废弃（v0.7.0 起默认就不删除云端文件；需要清理改用 --prune）。");
  }
  if (!values.source) {
    console.error("用法: deploy.mjs --source <发布目录> --bucket <桶名> [--prefix <子目录>] [--domain <xxx.budui.fun>] [--cert-dir <证书目录>] [--state-file <项目部署状态 JSON>] [--prune] [--dry-run] [--force] [--allow-existing-root] [--allow-project-source] [--allow-large-files] [--replace-domain-dns] [--no-spa]");
    process.exit(1);
  }
  const dry = values["dry-run"];
  console.log(`目标桶: oss://${env.bucket}（${env.region}）${values.bucket ? "（--bucket 显式指定）" : "（来自环境变量，建议项目固定用 --bucket 指定）"}`);
  if (dry) console.log("—— dry-run：只打印计划，不做任何修改 ——\n");

  // 域名归属前置校验：在任何写操作之前（防发错桶 + 改走 DNS）
  if (values.domain) await guardDomainOwnership(env, values.domain, values.force, dry);

  const prefix = values.prefix ? values.prefix.replace(/\/+$/, "") + "/" : "";
  if (values.domain && prefix) {
    throw new Error("自定义域名不能与 --prefix 混用：OSS 域名绑定始终指向 bucket 根路径。请为独立站点创建独立 bucket。");
  }
  const maxFileSizeMb = Number(values["max-file-size-mb"]);
  if (!Number.isFinite(maxFileSizeMb) || maxFileSizeMb <= 0) throw new Error("--max-file-size-mb 必须是正数。");
  // realpath 统一 8.3 短路径/符号链接，避免 relative() 算出绝对路径当 key
  const source = await realpath(values.source);
  const files = await walk(source, source);
  if (!files.some((file) => file.key === "index.html")) throw new Error("发布目录缺少 index.html。");
  const hazards = findReleaseHazards(files, maxFileSizeMb * 1024 * 1024);
  const blocked = [
    ...(values["allow-project-source"] ? [] : hazards.development),
    ...(values["allow-large-files"] ? [] : hazards.large),
  ];
  if (blocked.length) {
    throw new Error(`发布目录不是干净产物，拒绝上传：${blocked.slice(0, 8).join("；")}${blocked.length > 8 ? "；…" : ""}\n请创建只含运行资源的发布目录（如 dist/）。开发文件需 --allow-project-source；大文件需 --allow-large-files，并先确认它确实是站点资源。`);
  }

  const OSS = await loadOss();
  const client = new OSS({
    accessKeyId: env.accessKeyId,
    accessKeySecret: env.accessKeySecret,
    bucket: env.bucket,
    region: env.region,
  });

  // bucket 不存在则创建；每次确保公共读（静态网站需要）
  let fresh = false;
  try {
    await client.getBucketInfo(env.bucket);
  } catch {
    if (dry) {
      console.log(`[dry-run] bucket ${env.bucket} 不存在，正式运行将自动创建`);
    } else {
      console.log(`bucket ${env.bucket} 不存在，自动创建…`);
      await client.putBucket(env.bucket);
    }
    fresh = true;
  }
  const existingObjects = fresh ? [] : await listObjectNames(client, prefix);
  if (!fresh && !prefix && existingObjects.length && !values["allow-existing-root"]) {
    throw new Error(`bucket ${env.bucket} 根路径已有 ${existingObjects.length} 个对象。为避免覆盖同 bucket 的其他站点，拒绝部署。请改用独立 bucket；仅在已确认该根路径完全属于当前站点时才加 --allow-existing-root。`);
  }
  if (!dry) {
    const acl = (await client.getBucketACL(env.bucket)).acl || "private";
    if (acl !== "public-read") {
      try {
        await signedOss(env, "DELETE", "publicAccessBlock"); // 关闭 bucket 级阻止公共访问
      } catch { /* 未开启则忽略 */ }
      try {
        await client.putBucketACL(env.bucket, "public-read");
        console.log(`bucket 已设为公共读${fresh ? "" : "（原 " + acl + "）"}`);
      } catch (e) {
        throw new Error(`设置公共读失败: ${e.message}\n请到 OSS 控制台 → ${env.bucket} → 权限管理 → 阻止公共访问，手动关闭后重试。`);
      }
    }
    // 匿名访问自检；失败则尝试关闭账号级"阻止公共访问"并重设 ACL
    const probe = await fetch(`https://${env.bucket}.${env.region}.aliyuncs.com/index.html`, { method: "HEAD" });
    if (!probe.ok) {
      console.log("匿名访问被拒，尝试关闭“阻止公共访问”（bucket 级 + 账号级）并重设公共读…");
      try { await signedOss(env, "DELETE", "publicAccessBlock"); } catch { /* 未开启则忽略 */ }
      try {
        await signedOss(env, "PUT", "publicAccessBlock",
          '<?xml version="1.0" encoding="UTF-8"?><PublicAccessBlockConfiguration><BlockPublicAccess>false</BlockPublicAccess></PublicAccessBlockConfiguration>',
          "application/xml", true);
      } catch { /* 无权限则忽略 */ }
      await client.putBucketACL(env.bucket, "public-read");
    }
  }

  console.log(`待上传 ${files.length} 个文件 → oss://${env.bucket}/${prefix}`);

  for (const f of files) {
    const mime = MIME[extname(f.local).toLowerCase()] || "application/octet-stream";
    if (dry) { console.log(`  [将上传] ${prefix}${f.key}`); continue; }
    const body = await readFile(f.local);
    // html/js/css 不缓存，其余缓存 1 天，避免发版后浏览器用旧资源
    const cache = /\.(html|js|css)$/.test(f.key) ? "no-cache" : "max-age=86400";
    const key = `${prefix}${f.key}`;
    await client.put(key, body, { headers: { "Content-Type": mime, "Cache-Control": cache } });
    console.log(`  ✓ ${key}`);
  }

  // 清点目标前缀内的云端多余旧文件；删除必须显式 --prune（先备份再删）
  const remote = dry && fresh ? [] : await listObjectNames(client, prefix);
  const localKeys = new Set(files.map((f) => `${prefix}${f.key}`));
  const stale = remote.filter((k) => !localKeys.has(k));
  if (stale.length && !values.prune) {
    console.log(`发现 ${stale.length} 个云端多余旧文件，本次未删除（确认要清理加 --prune，删除前会备份到 _trash/）。`);
  }
  if (stale.length && values.prune) {
    // 多站点桶保护：清根前缀时，桶若还绑着 --domain 以外的域名，清理会殃及其他站点
    const bound = await listBucketCnames(env);
    const others = bound.filter((d) => d !== values.domain);
    if (!prefix && others.length && !values.force) {
      console.error(`\n中止：--prune 要清理 oss://${env.bucket}/ 根前缀，但该桶还绑着其他域名: ${others.join("、")}。`);
      console.error(`这通常意味着多个站点共用此桶，清理会连带删掉别的站。确认只此一站请加 --force；多站请改用独立 bucket。未做任何修改。`);
      process.exit(1);
    }
    const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    console.log(`${dry ? "[dry-run] 将清理" : "清理"} ${stale.length} 个云端多余旧文件${dry ? "" : "（已备份到 _trash/" + stamp + "/）"}…`);
    if (!dry) {
      for (const k of stale) await client.copy(`_trash/${stamp}/${k}`, k);
      for (let i = 0; i < stale.length; i += 100) {
        await client.deleteMulti(stale.slice(i, i + 100).map((k) => ({ key: k })));
      }
    } else {
      stale.forEach((k) => console.log(`  [将删除] ${k}`));
    }
  }

  if (dry) {
    console.log(`\n[dry-run] 计划完成：上传 ${files.length} 个、删除 ${values.prune ? stale.length : 0} 个；网站托管 index=index.html error=${prefix}index.html${values.domain ? `；域名 ${values.domain} 将绑定（归属校验已通过）` : ""}。`);
    console.log(`去掉 --dry-run 正式执行。`);
    return;
  }

  // 静态网站托管：index 首页 + 404 回退（SPA 路由）
  const indexKey = prefix ? `${prefix}index.html` : "index.html";
  await client.putBucketWebsite(env.bucket, {
    index: "index.html",
    error: indexKey,
    subDirType: 0,
  });

  const host = values.domain || `${env.bucket}.${env.region}.aliyuncs.com`;
  let scheme = "http";
  let domainBound = false;
  console.log(`\n部署完成 ✔`);

  // 自定义域名：先 PutCname 绑定（含归属验证），绑定成功后才改 CNAME 指向 —— 绑定失败不动 DNS
  if (values.domain) {
    const target = `${env.bucket}.${env.region}.aliyuncs.com`;
    console.log(`配置自定义域名 ${values.domain}…`);
    let cert, key;
    if (values["cert-dir"]) {
      try {
        cert = await readFile(join(values["cert-dir"], "cert.pem"), "utf8");
        key = await readFile(join(values["cert-dir"], "key.pem"), "utf8");
      } catch {
        console.warn(`  ⚠ 证书目录读取失败（需要 cert.pem 和 key.pem），将以 HTTP-only 绑定域名`);
      }
    }
    const tryBind = async () => {
      try {
        await putCname(env, values.domain, cert, key);
        domainBound = true;
        if (cert) scheme = "https";
        console.log(cert ? `  ✓ 域名已绑定并开启 HTTPS（证书需覆盖 ${values.domain}）` : `  ✓ 域名已绑定（HTTP）`);
        return true;
      } catch (e) {
        if (String(e.message).includes("NeedVerifyDomainOwnership")) {
          console.log(`  域名归属验证：创建 CnameToken 并添加 TXT 记录…`);
          const { token } = await createCnameToken(env, values.domain);
          let txtOk = true;
          try {
            await ensureDnsRecord(env, `_dnsauth.${values.domain}`, "TXT", token, true);
          } catch (e2) {
            txtOk = false;
            console.warn(`  ⚠ TXT 记录添加失败，请手动添加：主机记录 _dnsauth、类型 TXT、记录值 ${token}`);
          }
          if (txtOk) {
            console.log(`  等待 TXT 记录生效（约 1-2 分钟）…`);
            await new Promise((r) => setTimeout(r, 90_000));
          }
          await putCname(env, values.domain, cert, key);
          domainBound = true;
          if (cert) scheme = "https";
          console.log(cert ? `  ✓ 域名已绑定并开启 HTTPS（证书需覆盖 ${values.domain}）` : `  ✓ 域名已绑定（HTTP）`);
          return true;
        }
        console.warn(`  ⚠ 域名绑定失败（DNS 保持原样，站点不受影响）: ${e.message}`);
        return false;
      }
    };
    const bound = await tryBind();
    if (bound) {
      try {
        await ensureDnsRecord(env, values.domain, "CNAME", target, values["replace-domain-dns"] || values.force);
      } catch (e) {
        console.warn(`  ⚠ DNS 记录未改写（可手动添加 CNAME ${values.domain} → ${target}；确认切换后加 --replace-domain-dns）: ${e.message}`);
      }
    }
    console.log(`  提示: DNS 生效一般数分钟内；证书每年需在阿里云控制台续领免费证书后更新 cert-dir 重跑。`);
  }

  if (values["state-file"]) {
    const statePath = values["state-file"];
    const state = {
      bucket: env.bucket,
      region: env.region,
      source,
      prefix: values.prefix || "",
      domain: domainBound ? values.domain : null,
      https: scheme === "https",
      updatedAt: new Date().toISOString(),
    };
    await mkdir(dirname(statePath), { recursive: true });
    await writeFile(statePath, `${JSON.stringify(state, null, 2)}\n`, "utf8");
    console.log(`部署状态已写入: ${statePath}`);
  }

  console.log(`访问地址: ${scheme}://${host}/${values.prefix || ""}`);
  if (!values["no-spa"]) console.log(`SPA 404 回退已配置（子目录路由刷新不 404）。`);
  if (!values.domain) console.log(`提示: OSS 默认域名仅 HTTP；如需 HTTPS 使用 --domain 绑定已备案的自有域名。`);
}

main().catch((e) => { console.error("部署失败:", e.message || e); process.exit(1); });
