#!/usr/bin/env python3
"""Read-only GitHub publication preflight for a local project."""
import json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()

def run(*args):
    p = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def git(*args): return run('git', *args)
def field(cmd):
    code, out, _ = git(*cmd)
    return out if code == 0 else None

report = {"project": str(ROOT), "blockers": [], "warnings": [], "missing_evidence": []}
def github_login(env=None):
    p = subprocess.run(['gh','api','user','--jq','.login'], text=True, capture_output=True, env=env)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

code, login, error = github_login()
if code:
    # Windows 证书吊销检查在受限网络中可能阻断 gh；仅对当前子进程启用 Go 备用证书链。
    fallback_env = os.environ.copy()
    fallback_env['GODEBUG'] = 'x509usefallbackroots=1'
    code, login, fallback_error = github_login(fallback_env)
    if not code:
        report['github_transport_workaround'] = 'GODEBUG=x509usefallbackroots=1（仅当前进程）'
    else:
        error = fallback_error or error
report['github_login'] = login if not code else None
if not report['github_login']: report['blockers'].append('GitHub CLI 未登录或无法读取当前身份。')
report['is_git_repository'] = git('rev-parse','--is-inside-work-tree')[0] == 0
if report['is_git_repository']:
    report['branch'] = field(('branch','--show-current'))
    report['head'] = field(('rev-parse','HEAD'))
    report['origin'] = field(('remote','get-url','origin'))
    report['status'] = field(('status','--short')).splitlines()
else:
    report['warnings'].append('尚未初始化 Git 仓库；可在确认新建仓库后初始化。')
    report['status'] = []
config = ROOT / '.budui-github-publish.json'
if config.exists():
    try: report['project_defaults'] = json.loads(config.read_text())
    except json.JSONDecodeError: report['blockers'].append('项目发布配置不是有效 JSON。')
else: report['project_defaults'] = {}
patterns = [r'^\.env($|\.)', r'\.pem$', r'\.key$', r'id_rsa$', r'credentials', r'secret', r'token']
hits = []
for path in ROOT.rglob('*'):
    if any(part in {'.git','node_modules','.venv','venv'} for part in path.parts): continue
    # 内置扫描器本身不是凭据；不因文件名含 secret 误阻断本 Skill 的发布。
    if path.name == 'secret_gate.py' and path.parent.name == 'scripts': continue
    if path.is_file() and any(re.search(pattern, path.name, re.I) for pattern in patterns): hits.append(str(path.relative_to(ROOT)))
report['sensitive_name_candidates'] = hits[:50]
if hits: report['blockers'].append('发现疑似秘密或凭据文件名；必须人工审核并排除后才能发布。')
for name in ['README.md','LICENSE','.gitignore']:
    report[name] = (ROOT / name).exists()
if not report['README.md']: report['warnings'].append('缺少 README.md。')
if not report['.gitignore']: report['warnings'].append('缺少 .gitignore。')
print(json.dumps(report, ensure_ascii=False, indent=2))
