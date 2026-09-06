#!/usr/bin/env python3
"""Fail-closed redacted secret scan of worktree and Git history."""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    args = parser.parse_args()
    root = args.project.resolve()
    if not root.is_dir() or not shutil.which('gitleaks'):
        print(json.dumps({'ok': False, 'reason': 'Valid project directory and gitleaks installation required'}))
        return 2
    modes = ['dir']
    git = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    if git.returncode == 0:
        if Path(git.stdout.strip()).resolve() != root:
            print(json.dumps({'ok': False, 'reason': 'Select the repository root; refusing parent history ambiguity'}))
            return 2
        modes.append('git')
    results = []
    with tempfile.TemporaryDirectory(prefix='budui-secret-check-') as tmp:
        # Empty config prevents repository-supplied allowlists disabling checks.
        config = Path(tmp) / 'config.toml'
        config.write_text('[extend]\nuseDefault = true\n')
        for mode in modes:
            report = Path(tmp) / (mode + '.json')
            cmd = ['gitleaks', mode, str(root), '--redact=100', '--no-banner', '--exit-code', '1', '--config', str(config), '--gitleaks-ignore-path', str(Path(tmp)/'absent'), '--report-format', 'json', '--report-path', str(report)]
            cmd += ['--ignore-gitleaks-allow', '--max-archive-depth', '3']
            if mode == 'git':
                cmd += ['--log-opts=--all --full-history']
            try:
                run = subprocess.run(cmd, capture_output=True, timeout=300)
                findings = json.loads(report.read_text()) if report.exists() else []
                results.append({'mode': mode, 'exit_code': run.returncode, 'findings': [{'file': x.get('File'), 'rule': x.get('RuleID'), 'line': x.get('StartLine')} for x in findings]})
            except (subprocess.TimeoutExpired, ValueError, OSError):
                results.append({'mode': mode, 'exit_code': 2, 'error': 'Scan failed; publishing blocked'})
    ok = all(r['exit_code'] == 0 for r in results)
    print(json.dumps({'ok': ok, 'results': results}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
