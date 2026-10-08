# -*- coding: utf-8 -*-
"""四件套 → 飞书推送（lark-cli）

用法:
  python render_push.py --stats <stats.json> --files <前缀> --to <ou_xxx 或 oc_xxx>
  python render_push.py --stats <stats.json> --files <前缀> --to self
  python render_push.py --stats <stats.json> --files <前缀> --to self --dry-run

产出: 一条摘要卡 + 4 份文件消息（Excel / HTML / PNG / PDF）
退出码: 0=全部成功 / 4=部分失败 / 5=未找到 lark-cli / 6=未找到收件人

设计要点（均为实测约束，勿擅自简化）:
  1. lark-cli 的 --file/--image 只接受 **相对路径**，绝对路径与 .. 会被直接拒绝。
     故必须先 os.chdir 到文件所在目录，再传相对文件名。
  2. PNG 必须走 --image（走 --file 会当普通附件，飞书不预览）；
     Excel/PDF/HTML 走 --file。二者通道不同，不可混用。
  3. 图片通道有 ~10MB 上限；超限自动降级为 --file 并在摘要里标注。
  4. bot 身份可直接发给用户 open_id；未经确认不得改为群发。
"""
SCRIPT_INTERFACE = "cli"

import sys, os, re, json, argparse, subprocess, shutil, pathlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
C.setup_stdout()

EXIT_OK = 0
EXIT_PARTIAL = 4
EXIT_NO_CLI = 5
EXIT_NO_TARGET = 6

# Windows 本地回退路径；容器与 Linux 环境优先走 PATH。
CLI_CANDIDATES = [
    os.path.expandvars(r'%USERPROFILE%\.workbuddy\binaries\node\cli-connector-packages\lark-cli.CMD'),
    os.path.expandvars(r'%USERPROFILE%\.workbuddy\binaries\node\cli-connector-packages\lark-cli'),
]
IMAGE_LIMIT = 9 * 1024 * 1024     # 飞书图片通道 ~10MB，留 1MB 余量
SEND_TIMEOUT = 180


def find_cli():
    override = os.environ.get('LARK_CLI_PATH', '').strip()
    if override and os.path.isfile(override):
        return override
    for name in ('lark-cli', 'lark'):
        p = shutil.which(name)
        if p:
            return p
    for c in CLI_CANDIDATES:
        if c and os.path.exists(c):
            return c
    return None


def _read_config_user_open_id(config_path=None):
    """读取 lark-cli 配置中的全部合法 open_id；多账号由调用方拒绝歧义。"""
    path = pathlib.Path(config_path) if config_path else pathlib.Path.home() / '.lark-cli' / 'config.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    found = []

    def add(value):
        if isinstance(value, str) and re.fullmatch(r'ou_[A-Za-z0-9]+', value) and value not in found:
            found.append(value)

    # v1.x: apps[].users[].user_open_id / userOpenId
    for app in data.get('apps') or []:
        if not isinstance(app, dict):
            continue
        for user in app.get('users') or []:
            if isinstance(user, dict):
                add(user.get('user_open_id'))
                add(user.get('userOpenId'))
    # 旧版扁平格式
    add(data.get('user_open_id'))
    add(data.get('userOpenId'))
    return found


def run_result(cli, args, cwd=None):
    try:
        r = subprocess.run([cli] + args, capture_output=True, text=True,
                           timeout=SEND_TIMEOUT, cwd=cwd, encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        return {'output': '', 'returncode': None, 'timed_out': True}
    return {'output': (r.stdout or '') + (r.stderr or ''), 'returncode': r.returncode, 'timed_out': False}


def resolve_target(cli, to, config_path=None):
    """--to self 时优先 dry-run 身份；失败后只接受无歧义的本地配置身份。"""
    if to and to != 'self':
        return to, None, 'explicit'
    probe = run_result(cli, ['im', '+messages-send', '--user-id', 'ou_probe',
                             '--text', 'probe', '--dry-run'])
    output = probe['output']
    m = re.search(r'"(?:user_open_id|userOpenId)"\s*:\s*"(ou_[A-Za-z0-9]+)"', output)
    if probe['returncode'] == 0 and m:
        return m.group(1), None, 'dry_run'
    candidates = _read_config_user_open_id(config_path)
    if len(candidates) == 1:
        return candidates[0], None, 'config_fallback'
    if len(candidates) > 1:
        return None, '配置文件存在多个 user_open_id，请显式指定 --to ou_xxx', None
    detail = 'dry-run 超时' if probe['timed_out'] else f'dry-run 退出码 {probe["returncode"]}'
    return None, f'{detail}，且未在配置文件中找到唯一 user_open_id', None


def run(cli, args, cwd=None):
    return run_result(cli, args, cwd)['output'] or None


def send_text(cli, target, text, is_chat=False):
    flag = '--chat-id' if is_chat else '--user-id'
    out = run(cli, ['im', '+messages-send', flag, target, '--text', text])
    return bool(out and '"ok": true' in out.replace(' ', ' ')), out


def send_file(cli, target, path, as_image=False, is_chat=False):
    """必须传相对路径：切到文件所在目录后传文件名。"""
    p = pathlib.Path(path).resolve()
    if not p.is_file():
        return False, f'文件不存在: {p}'
    flag = '--chat-id' if is_chat else '--user-id'
    kind = '--image' if as_image else '--file'
    out = run(cli, ['im', '+messages-send', flag, target, kind, p.name],
              cwd=str(p.parent))
    ok = bool(out and '"ok": true' in out)
    return ok, out


def build_summary(stats, sent, failed, note=''):
    m = stats.get('meta', {})
    m1 = stats.get('m1', {})
    m2 = stats.get('m2', {})
    m9 = stats.get('m9') or {}
    topic = m.get('topic', '专项')
    period = m.get('period_name', '周报')
    n = m2.get('n', 0)
    pos = m2.get('positive_rate')
    neu = m2.get('neutral_rate')
    neg = m2.get('negative_rate')
    pen = m2.get('penetration')
    uni = m2.get('universe_label', '')

    lines = [f'【{topic}】{period}分析完成']
    if n:
        seg = f'主口径 {n:,} 条'
        if pen is not None:
            seg += f'｜渗透率 万分之 {pen:g}'
            if uni:
                seg += f'（{uni}）'
        lines.append(seg)
    if neg is not None:
        # 三档情感分布（正面/中性/负面）；旧 stats 缺正面字段时回退只报负面率
        if pos is not None or neu is not None:
            lines.append(f'正面 {pos or 0:.1f}%｜中性 {neu or 0:.1f}%｜负面 {neg:.1f}%')
        else:
            lines.append(f'负面率 {neg:.1f}%')

    # 关键结论前置：决策层看这一段就够了
    insights = m9.get('insights') or []
    if insights:
        lines.append('')
        lines.append('■ 关键洞察')
        for it in insights[:4]:
            lines.append(f"[{it.get('priority', '')}] {it.get('title', '')}")
        if len(insights) > 4:
            lines.append(f'另有 {len(insights) - 4} 条见明细')

    actions = m9.get('actions') or []
    if actions:
        lines.append('')
        lines.append('■ 建议动作')
        for ac in actions[:3]:
            lines.append(f"[{ac.get('priority', '')}] {ac.get('action', '')}（{ac.get('owner', '')}）")
        if len(actions) > 3:
            lines.append(f'另有 {len(actions) - 3} 项见明细')

    cov = m1.get('coverage_note')
    if cov:
        lines.append('')
        lines.append(cov)
    lines.append('')
    lines.append(f'附件 {len(sent)} 份' + (f'，{len(failed)} 份失败' if failed else ''))
    if note:
        lines.append(note)
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description='把四件套推送到飞书')
    ap.add_argument('--stats', required=True, help='stats.json 路径')
    ap.add_argument('--files', required=True, help='四件套输出前缀（不含扩展名）')
    ap.add_argument('--to', required=True, help='"self" 或 ou_xxx（用户）或 oc_xxx（群）')
    ap.add_argument('--dry-run', action='store_true', help='只预览不发送')
    ap.add_argument('--no-image', action='store_true', help='PNG 也走文件通道')
    a = ap.parse_args()

    cli = find_cli()
    if not cli:
        print('SKIPPED: 未找到 lark-cli，跳过飞书推送。')
        print('  安装：npx skills add larksuite/cli -g -y')
        return EXIT_NO_CLI

    target, err, target_source = resolve_target(cli, a.to)
    if not target:
        print(f'SKIPPED: 未能确定收件人（{err}）。')
        return EXIT_NO_TARGET
    is_chat = target.startswith('oc_')

    base = pathlib.Path(a.files)
    if base.suffix.lower() in ('.xlsx', '.html', '.png', '.pdf'):
        base = base.with_suffix('')
    stem = base.name
    parent = base.parent

    # 四件套命名：Excel 用「<主题>专项简报_明细」，其余用「<主题>专项简报」；
    # 候选串同时兼容旧「问题分析」命名，勿删任一候选。
    def locate(ext):
        for cand in (parent / f'{stem}_明细{ext}',      # 明细: xlsx
                     parent / f'{stem}简报{ext}',        # 简报: html/png/pdf
                     parent / f'{stem}{ext}'):           # 无后缀
            if cand.exists():
                return cand
        return parent / f'{stem}{ext}'                   # 不存在也返回，用于报缺失

    items = [
        (locate('.xlsx'), False),
        (locate('.html'), False),
        (locate('.png'),  not a.no_image),
        (locate('.pdf'),  False),
    ]
    missing = [p.name for p, _ in items if not p.exists()]
    todo = [(p, img) for p, img in items if p.exists()]

    print(f'收件人：{target}{"（群）" if is_chat else ""}｜身份来源：{target_source}')
    print(f'待发送 {len(todo)} 份' + (f'，缺失 {missing}' if missing else ''))
    if a.dry_run:
        for p, img in todo:
            print(f'  [dry-run] {p.name}  → {"图片通道" if img else "文件通道"}')
        return EXIT_OK

    try:
        stats = json.load(open(a.stats, encoding='utf-8'))
    except Exception:
        stats = {}

    sent, failed, notes = [], [], []
    # 先发摘要，让文件消息有上下文
    ok, _ = send_text(cli, target, build_summary(stats, todo, [], ''), is_chat)
    if not ok:
        notes.append('摘要消息发送失败')

    for p, as_image in todo:
        big = p.stat().st_size > IMAGE_LIMIT
        use_image = as_image and not big
        if big and as_image:
            notes.append(f'{p.name} 超过图片上限，已按附件发送')
        ok, out = send_file(cli, target, str(p), as_image=use_image, is_chat=is_chat)
        if ok:
            sent.append(p.name)
            print(f'  OK  {p.name}  {p.stat().st_size/1024:.0f}KB'
                  f'  ({"图片" if use_image else "文件"})')
        else:
            failed.append(p.name)
            tail = (out or '')[-240:].replace('\n', ' ')
            print(f'  FAIL {p.name}  {tail}')

    print(f'\n完成：成功 {len(sent)} / {len(todo)}')
    for n in notes:
        print(f'  注：{n}')
    return EXIT_PARTIAL if failed else EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
