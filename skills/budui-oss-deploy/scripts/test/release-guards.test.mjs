import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const script = fileURLToPath(new URL("../deploy.mjs", import.meta.url));
const env = { ...process.env, OSS_ACCESS_KEY_ID: "test", OSS_ACCESS_KEY_SECRET: "test", OSS_BUCKET: "test", OSS_REGION: "oss-cn-hongkong" };

function run(source, extra = []) {
  try {
    execFileSync(process.execPath, [script, "--source", source, ...extra], { env, encoding: "utf8", stdio: "pipe" });
    return "";
  } catch (error) {
    return `${error.stdout || ""}${error.stderr || ""}`;
  }
}

test("拒绝包含开发文件的发布目录", () => {
  const root = mkdtempSync(join(tmpdir(), "oss-deploy-test-"));
  mkdirSync(join(root, "docs"));
  writeFileSync(join(root, "index.html"), "<title>test</title>");
  writeFileSync(join(root, "docs", "internal.md"), "internal");
  assert.match(run(root), /发布目录不是干净产物/);
});

test("拒绝自定义域名与对象前缀混用", () => {
  const root = mkdtempSync(join(tmpdir(), "oss-deploy-test-"));
  writeFileSync(join(root, "index.html"), "<title>test</title>");
  assert.match(run(root, ["--domain", "ticket.example.com", "--prefix", "ticket"]), /不能与 --prefix 混用/);
});
