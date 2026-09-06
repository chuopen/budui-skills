#!/usr/bin/env python3
"""Independent GitHub readback after a confirmed publication."""
import json, subprocess, sys
if len(sys.argv) != 3:
    raise SystemExit('Usage: verify_remote.py OWNER/REPO BRANCH')
repo, branch = sys.argv[1:]
p = subprocess.run(['gh','repo','view',repo,'--json','nameWithOwner,url,visibility,defaultBranchRef'], text=True, capture_output=True)
if p.returncode:
    raise SystemExit(p.stderr.strip())
data = json.loads(p.stdout)
p = subprocess.run(['gh','api',f'repos/{repo}/commits/{branch}','--jq','.sha'], text=True, capture_output=True)
data['branch'] = branch
data['branch_head'] = p.stdout.strip() if p.returncode == 0 else None
data['verified'] = bool(data['branch_head'])
print(json.dumps(data, ensure_ascii=False, indent=2))
