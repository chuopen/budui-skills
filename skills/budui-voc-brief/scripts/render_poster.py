# -*- coding: utf-8 -*-
"""stats.json → 多预设信息图海报 HTML（版式锁定，见 references/ui-spec.md）

用法: python render_poster.py --stats reports/stats.json --out 简报.html
"""
import sys, os, json, math, argparse, re, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
C.setup_stdout()

SVG_DIR = os.path.join(C.skill_root(), 'assets', 'svg')
THEME_DIR = os.path.join(C.skill_root(), 'assets', 'theme')
UI_THEME_FILE = 'assets/ui-themes.json'
REQUIRED_RESOURCES = (
    UI_THEME_FILE,
    'assets/icon-map.json',
    'assets/svg/icon-generic.svg',
    'assets/theme/hero-generic.svg',
)

# 语义色（不随色彩预设切换）：负面红 / 正面绿
GOOD_GREEN = '#079781'
GOOD_GREEN_LIGHT = '#9CD6CB'

SHAPE_ICON = {
    '异响类': 'issue-noise.svg', '伸缩卡滞类': 'issue-stuck.svg', '卡滞类': 'issue-stuck.svg',
    '开合失效类': 'issue-stuck.svg', '失灵类': 'issue-fail.svg', '损坏类': 'issue-broken.svg',
    '脱落类': 'issue-fall.svg', '外观类': 'issue-appearance.svg', '间隙类': 'issue-gap.svg',
    '性能类': 'issue-fail.svg', '咨询类': 'issue-other.svg', '设计抱怨类': 'issue-other.svg',
    '其他': 'issue-other.svg',
}
MOD_ICON = {
    'm1': 'mod-data.svg', 'm2': 'mod-scale.svg', 'm3': 'mod-scale.svg', 'm4': 'mod-structure.svg',
    'm5': 'mod-trend.svg', 'm6': 'mod-spill.svg', 'm7': 'mod-focus.svg', 'm8': 'mod-voice.svg',
    'm9': 'mod-insight.svg', 'praise': 'mod-praise.svg',
}
DONUT_COLORS = ['#F5820B', '#FFB347', '#FFD8A8', '#E64340', '#8C7A66', '#D9D3CB']

THEME_REPLACEMENTS = {
    '#F5820B': '--primary', '#EA7000': '--primary-deep', '#C4620A': '--primary-dark',
    '#FFA53B': '--primary-bright', '#FFB347': '--primary-mid', '#FFCF8C': '--primary-light',
    '#FFD8A8': '--primary-pale', '#FFF7EC': '--primary-bg', '#FFFBF4': '--primary-card',
    '#F7E7CF': '--primary-border', '#F0E2CE': '--primary-dash', '#F2E7D8': '--primary-grid',
    '#F7F2EA': '--primary-base', '#FFF3E2': '--primary-head', '#FFFDFA': '--primary-card',
}

def theme_catalog():
    data = C.load_json(UI_THEME_FILE, {})
    return data, data.get('presets') or {}

def missing_resources():
    root = C.skill_root()
    return [rel for rel in REQUIRED_RESOURCES if not os.path.isfile(os.path.join(root, rel))]

def resolve_theme(requested=''):
    """Accept the preset key, display name or a Chinese/English alias."""
    data, presets = theme_catalog()
    default = data.get('default', 'amber-dawn')
    text = str(requested or '').strip().lower()
    for key, preset in presets.items():
        words = [key, str(preset.get('name', '')).lower()] + [str(x).lower() for x in preset.get('aliases', [])]
        if text and text in words:
            return key, preset
    return default, presets.get(default, {})

def apply_theme(html_text, preset):
    tokens = preset.get('tokens') or {}
    if not tokens:
        # 不把可用的默认色替换成未定义 CSS 变量，避免静默产出损坏海报。
        return html_text
    css = ':root{' + ''.join(f'--{k.replace("_", "-")}:{v};' for k, v in tokens.items()) + '}'
    for literal, var in THEME_REPLACEMENTS.items():
        html_text = html_text.replace(literal, f'var({var})')
    return html_text.replace('<style>', f'<style>{css}', 1)

def svg(name, size, color=None):
    p = os.path.join(SVG_DIR, name or '')
    if not name or not os.path.exists(p):
        p = os.path.join(SVG_DIR, 'icon-generic.svg')
        if not os.path.exists(p):
            return ''
    s = open(p, encoding='utf-8').read()
    s = re.sub(r'width="100" height="100"', f'width="{size}" height="{size}"', s)
    if color:
        s = s.replace('#F5820B', color)
    return s

def theme_svg(icon):
    """Use the matching cover visual, then its group, then the generic visual."""
    icon = os.path.basename(icon or '')
    if not re.fullmatch(r'icon-[a-z0-9-]+\.svg', icon):
        icon = 'icon-generic.svg'
    imap = C.load_json('assets/icon-map.json', {})
    choices = [icon, (imap.get('icon_group') or {}).get(icon), 'icon-generic.svg']
    for name in choices:
        if not name:
            continue
        path = os.path.join(THEME_DIR, name.replace('icon-', 'hero-', 1))
        if os.path.isfile(path):
            return open(path, encoding='utf-8').read()
    return ''

def esc(x):
    return html.escape(str(x if x is not None else ''))

# ---------- 图表 ----------
def trend_svg(rows):
    if not rows:
        return ''
    n = len(rows)
    x0, x1, y0, y1 = 46, 424, 34, 176
    h = y1 - y0
    step = (x1 - x0) / n
    mx_avg = max([r['avg'] for r in rows] + [1]) * 1.25
    mx_pct = max([r['pct'] for r in rows] + [1]) * 1.25
    by = lambda v: y1 - (v / mx_avg) * h
    ly = lambda v: y1 - (v / mx_pct) * h
    peak = max(rows, key=lambda r: r['n'])['key'] if rows else ''
    p = ['<svg viewBox="0 0 470 208" style="width:100%;height:auto" xmlns="http://www.w3.org/2000/svg">']
    p.append('<defs><linearGradient id="b0" x1="0" y1="0" x2="0" y2="1">'
             '<stop offset="0%" stop-color="#FFB347"/><stop offset="100%" stop-color="#F5820B"/></linearGradient>'
             '<linearGradient id="bp" x1="0" y1="0" x2="0" y2="1">'
             '<stop offset="0%" stop-color="#FF8A65"/><stop offset="100%" stop-color="#E64340"/></linearGradient></defs>')
    for i in range(4):
        v = mx_avg * i / 3
        yy = y1 - (v / mx_avg) * h
        p.append(f'<line x1="{x0}" y1="{yy:.1f}" x2="{x1}" y2="{yy:.1f}" stroke="#F2E7D8" stroke-width="1"/>')
        p.append(f'<text x="{x0-7}" y="{yy+3.5:.1f}" font-size="9" fill="#B9A88F" text-anchor="end">{v:.0f}</text>')
    for i in range(1, 5):
        yy = ly(mx_pct * i / 4)
        p.append(f'<text x="{x1+7}" y="{yy+3.5:.1f}" font-size="9" fill="#E64340" text-anchor="start">{mx_pct*i/4:.0f}</text>')
    bw = max(12, min(30, step * 0.5))
    for i, r in enumerate(rows):
        cx = x0 + step * (i + 0.5)
        yv = by(r['avg'])
        gid = 'bp' if r['key'] == peak else 'b0'
        p.append(f'<rect x="{cx-bw/2:.1f}" y="{yv:.1f}" width="{bw:.1f}" height="{y1-yv:.1f}" fill="url(#{gid})" rx="3"/>')
        if bw >= 20:
            p.append(f'<text x="{cx:.1f}" y="{yv+15:.1f}" font-size="10" font-weight="800" fill="#fff" text-anchor="middle">{r["avg"]:g}</text>')
        p.append(f'<text x="{cx:.1f}" y="{y1+15:.1f}" font-size="10" fill="#8C8C8C" text-anchor="middle">{esc(r["label"])}</text>')
    pts = ' '.join(f'{x0+step*(i+0.5):.1f},{ly(r["pct"]):.1f}' for i, r in enumerate(rows))
    p.append(f'<polyline points="{pts}" fill="none" stroke="#E64340" stroke-width="2" stroke-linejoin="round"/>')
    for i, r in enumerate(rows):
        cx = x0 + step * (i + 0.5)
        p.append(f'<circle cx="{cx:.1f}" cy="{ly(r["pct"]):.1f}" r="3.4" fill="#fff" stroke="#E64340" stroke-width="2"/>')
    p.append(f'<text x="{x0-7}" y="20" font-size="9" fill="#C4620A" text-anchor="end">均值</text>')
    p.append(f'<text x="{x1+7}" y="20" font-size="9" fill="#E64340" text-anchor="start">万分比</text>')
    p.append('</svg>')
    return ''.join(p)

def donut_svg(data, total=None, center_label=None):
    if not data:
        return ''
    R, SW = 41, 21
    Cc = 2 * math.pi * R
    total = total or sum(v for _, v in data) or 1
    p = ['<svg viewBox="0 0 116 116" style="width:100px;height:100px;flex:0 0 auto" xmlns="http://www.w3.org/2000/svg">']
    # 先画完整浅色底环；规则未覆盖的负面声量留白，不伪装成任何业务分类。
    p.append(f'<circle cx="58" cy="58" r="{R}" fill="none" stroke="#F0F0F0" stroke-width="{SW}"/>')
    off = 0.0
    for i, (k, v) in enumerate(data):
        seg = v / total * Cc
        p.append(f'<circle cx="58" cy="58" r="{R}" fill="none" stroke="{DONUT_COLORS[i%6]}" stroke-width="{SW}" '
                 f'stroke-dasharray="{max(seg-1.5,0.6):.2f} {Cc-seg+1.5:.2f}" stroke-dashoffset="{-off:.2f}" '
                 f'transform="rotate(-90 58 58)"/>')
        off += seg
    p.append(f'<text x="58" y="55" font-size="17" font-weight="800" fill="#2B2B2B" text-anchor="middle">{center_label if center_label is not None else total}</text>')
    p.append('<text x="58" y="69" font-size="9" fill="#8C8C8C" text-anchor="middle">条</text>')
    p.append('</svg>')
    return ''.join(p)

def bar_rows(items, mx, color='#F5820B', suffix=''):
    out = []
    for k, v in items:
        w = max(v / mx * 100, 3) if mx else 3
        fill = ''
        if color == 'red':
            fill = ';background:linear-gradient(90deg,#FF8A65,#E64340)'
        elif color == 'green':
            fill = f';background:linear-gradient(90deg,{GOOD_GREEN_LIGHT},{GOOD_GREEN})'
        val_style = f' style="color:{GOOD_GREEN}"' if color == 'green' else ''
        out.append(f'<div class="rrow"><div class="rlab">{esc(k)}</div>'
                   f'<div class="rbar"><div class="rfill" style="width:{w:.1f}%{fill}"></div></div>'
                   f'<div class="rval"{val_style}>{v}</div></div>')
    return ''.join(out)

def sec(icon_key, title, right=''):
    ic = svg(MOD_ICON.get(icon_key, ''), 14)
    rt = f'<span class="sm">{right}</span>' if right else ''
    return f'<div class="t"><i></i>{ic}<span class="tt">{esc(title)}</span>{rt}</div>'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stats', help='stats.json path')
    ap.add_argument('--out', help='HTML output path')
    ap.add_argument('--theme', help='visual preset key, name or alias; overrides stats.json')
    ap.add_argument('--list-themes', action='store_true', help='print available visual presets and exit')
    ap.add_argument('--verify-resources', action='store_true', help='verify required runtime assets and exit')
    a = ap.parse_args()
    missing = missing_resources()
    if missing:
        print('[资源不完整] 渲染已中止，缺少：' + '、'.join(missing), file=sys.stderr)
        print('请将整个 assets/ 目录（含 JSON、svg、theme）随 scripts/ 一起复制到运行目录。', file=sys.stderr)
        return 2
    if a.verify_resources:
        print('OK: runtime resources complete')
        return 0
    if a.list_themes:
        _, presets = theme_catalog()
        for key, preset in presets.items():
            print(f'{key}\t{preset.get("name", key)}\t{preset.get("description", "")}')
        return
    if not a.stats or not a.out:
        ap.error('--stats and --out are required unless --list-themes is used')
    S = json.load(open(a.stats, encoding='utf-8'))
    M, m1, m2, m4, m5, m6, m7, m8 = (S['meta'], S['m1'], S['m2'], S['m4'], S['m5'],
                                     S['m6'], S['m7'], S['m8'])
    m3 = S.get('m3')
    public = S.get('public') or {}
    topic = M['topic']
    date_scope = M.get('analysis_date_range') or {}
    scope_start = date_scope.get('start') or M.get('date_from', '')
    scope_end = date_scope.get('end') or M.get('date_to', '')
    scope_label = date_scope.get('label') or M.get('period_name', '统计区间')
    header_period = f'{scope_label} · {scope_start.replace("-", "/")}–{scope_end.replace("-", "/")}'
    theme_key, theme = resolve_theme(a.theme or M.get('visual_theme'))

    # 总量卡 + 情感三分布（正面 ≥10 条出全貌，否则回退负面聚焦版式）
    pos_n = m2.get('positive_n') or 0
    neu_n = m2.get('neutral_n') or 0
    pos_pct = m2.get('positive_rate') or 0
    neu_pct = m2.get('neutral_rate') or 0
    show_full = pos_n >= 10
    neg = m2['negative_n']
    neg_pct = m2['negative_rate']
    svc = m6['service_total']
    svc_pct = round(svc / m2['n'] * 100) if m2['n'] else 0
    top_vp = [k for k, _ in m4['vp_top'][:2]]
    top_l2 = [k for k, _, _ in m6['l2'][:2]]
    top_pos_vp = [r[0] for r in (m2.get('vp_top_pos') or [])[:2] if r and r[0]]

    # 总量卡内嵌卡：全貌（三档情感）或聚焦（负面+外溢，原 1.0 版式）
    if show_full:
        def _emo_row(label, n_, pct_, color, tags=()):
            tag_html = ''
            if tags:
                spans = ''.join(f'<span class="tg" style="background:{color}">{esc(x)}</span>' for x in tags)
                tag_html = f'<div class="tags" style="justify-content:flex-end;margin-top:4px">{spans}</div>'
            light = GOOD_GREEN_LIGHT if color == GOOD_GREEN else ('#BFBFBF' if color == '#8C8C8C' else '#FF8A65')
            return (f'<div style="padding:8px 0 5px">'
                    f'<div class="share" style="padding:0">'
                    f'<div class="sl" style="font-weight:700;color:{color}">{label}</div>'
                    f'<div class="sv" style="color:{color}">{n_:,}'
                    f'<small style="font-size:10px;font-weight:400;color:#A8A8A8"> 条 · {pct_:g}%</small></div>'
                    f'<div class="pctbar"><b style="width:{min(pct_,100):.0f}%;'
                    f'background:linear-gradient(90deg,{light},{color})"></b></div>'
                    f'</div>{tag_html}</div>')
        split_html = (
            '<div class="split">'
            + _emo_row('正面', pos_n, pos_pct, GOOD_GREEN, top_pos_vp)
            + _emo_row('中性', neu_n, neu_pct, '#8C8C8C')
            + _emo_row('负面', neg, neg_pct, '#E64340', top_vp)
            + '</div>'
            + f'<div class="tsub" style="margin:9px 0 0 2px">外溢服务（关键词直命中）{svc} 条（相对主口径 {svc_pct}%）＝'
            f'未归入主口径、且命中冻结关键词并落在服务域的声音（每 1 条主口径伴随 {m6["ratio"]:g} 条）</div>'
        )
    else:
        split_html = f'''
    <div class="split">
      <div class="srow">
        <div class="sname">负面声音</div>
        <div class="snum">{neg}<small>条</small></div>
        <div class="tags">{''.join(f'<span class="tg">{esc(x)}</span>' for x in top_vp)}</div>
      </div>
      <div class="share">
        <div class="sl">负面率</div>
        <div class="sv" style="color:#C4620A">{neg_pct:g}%</div>
        <div class="pctbar"><b style="width:{min(neg_pct,100):.0f}%"></b></div>
      </div>
      <div class="srow">
        <div class="sname red">外溢服务</div>
        <div class="snum">{svc}<small>条</small></div>
        <div class="tags">{''.join(f'<span class="tg red">{esc(x)}</span>' for x in top_l2)}</div>
      </div>
      <div class="share">
        <div class="sl">相对主口径</div>
        <div class="sv" style="color:#E64340">{svc_pct}%</div>
        <div class="pctbar"><b class="red" style="width:{min(svc_pct,100):.0f}%"></b></div>
      </div>
    </div>
    <div class="tsub" style="margin:9px 0 0 2px">外溢服务 = 关键词直命中、未归入主口径且落在一级标签服务域的声音（每 1 条主口径伴随 {m6['ratio']:g} 条）</div>'''

    # 趋势数据条
    trend_strip = ''.join(
        f'<span>{esc(r["label"])} <b>{r["pct"]:g}</b></span>' for r in m5['rows'])

    # 基线对比
    baseline_html = ''
    if m3:
        t_rate, b_rate = m3['target_rate'] or 0, m3['baseline_rate'] or 0
        mx = max(t_rate, b_rate, 1)
        mult = f"{m3['multiple']:g}" if m3['multiple'] else '—'
        gap_note = (f"两车型声量基数差异 {m3['base_gap']}%，倍数可比性下降"
                    if m3['base_gap'] > 50 else
                    f"（{m3['target_label']} {m3['target_universe']:,} / {m3['baseline_label']} {m3['baseline_universe']:,} 条）")
        baseline_html = f'''
  <div class="sec">
    {sec('m3', f"{m3['target_label']} vs {m3['baseline_label']} 声量强度对标", '每万条声音中的声量（万分比）')}
    <div class="box">
      <div style="display:flex;align-items:baseline;gap:8px">
        <span style="font-size:38px;font-weight:800;color:#E64340;line-height:1;font-variant-numeric:tabular-nums">{mult}</span>
        <span style="font-size:14px;font-weight:800;color:#E64340">倍</span>
        <span style="font-size:10.5px;color:#8C8C8C;margin-left:auto;text-align:right;line-height:1.5">{gap_note}</span>
      </div>
      <div style="margin-top:13px">
        <div class="rrow" style="grid-template-columns:60px 1fr 52px">
          <div class="rlab" style="font-weight:700;color:#E64340">{esc(m3['target_label'])}</div>
          <div class="rbar" style="height:16px"><div class="rfill" style="width:{t_rate/mx*100:.1f}%;background:linear-gradient(90deg,#FF8A65,#E64340)"></div></div>
          <div class="rval" style="color:#E64340">{t_rate:g}</div></div>
        <div class="rrow" style="grid-template-columns:60px 1fr 52px;margin-bottom:0">
          <div class="rlab" style="font-weight:700">{esc(m3['baseline_label'])}</div>
          <div class="rbar" style="height:16px"><div class="rfill" style="width:{b_rate/mx*100:.1f}%;background:#D9D3CB"></div></div>
          <div class="rval" style="color:#8C8C8C">{b_rate:g}</div></div>
      </div>
      <div style="font-size:10.5px;color:#8C8C8C;margin-top:11px;padding-top:10px;border-top:1px dashed #F0E2CE;line-height:1.75">
        {esc(m3['target_label'])} 主口径 <b style="color:#C4620A">{m3['target_n']} 条</b>（{m3['target_universe']:,} 条中），
        {esc(m3['baseline_label'])} <b style="color:#C4620A">{m3['baseline_n']} 条</b>（{m3['baseline_universe']:,} 条中）。
        情感分布 <b style="color:#C4620A">正面 {pos_pct:g}% / 中性 {neu_pct:g}% / 负面 {neg_pct:g}%</b>。
      </div>
    </div>
  </div>'''

    # 三档主题独立归并；此处仅展示负面风险主题，覆盖不足时不展示，防止把未归并记录伪装成业务分类。
    excl = m4.get('exclusive') or []
    neg_n = m4.get('negative_n', m2.get('negative_n', 0))
    coverage = m4.get('shape_coverage', 0)
    shape_displayable = bool(excl and neg_n and coverage >= 85.0)
    shown_shapes = excl[:6] if shape_displayable else []
    unclassified_n = m4.get('unclassified_n', 0)
    unclassified_top = '、'.join(f'{x[0]}({x[1]})' for x in (m4.get('unclassified_vp_top') or [])[:3]) or '无'
    all_themes = m4.get('themes') or {}
    positive_theme = all_themes.get('正面') or {}
    neutral_theme = all_themes.get('中性') or {}
    nonnegative_theme_note = ''
    if positive_theme.get('total', 0) or neutral_theme.get('total', 0):
        nonnegative_theme_note = (f'正面主题规则覆盖 {positive_theme.get("coverage", 0):g}%'
                                  f'（{positive_theme.get("classified_n", 0)}/{positive_theme.get("total", 0)}）｜'
                                  f'中性主题规则覆盖 {neutral_theme.get("coverage", 0):g}%'
                                  f'（{neutral_theme.get("classified_n", 0)}/{neutral_theme.get("total", 0)}）；三档主题独立统计，详见 Excel。')

    # 负面主题图例（彩色图标替代色块）
    shape_items = []
    for i, (k, v, pc) in enumerate(shown_shapes):
        icon = svg(SHAPE_ICON.get(k, 'issue-other.svg'), 17, DONUT_COLORS[i % 6])
        shape_items.append(f'<div class="lgrow">{icon}<span class="lgn">{esc(k)}</span>'
                           f'<b>{v}</b><em>{pc:g}%</em></div>')
    shape_html = (
        f'<div>{sec("m4", "负面风险主题", f"负面 {neg_n} 条 · 已归并 {coverage:g}%")}'
        f'<div class="dwrap">{donut_svg([(k, v) for k, v, _ in shown_shapes], total=neg_n, center_label=sum(v for _, v, _ in shown_shapes))}'
        f'<div style="flex:1;min-width:0">{"".join(shape_items)}</div></div></div>'
        if shape_displayable else
        f'<div>{sec("m4", "负面风险主题", f"规则覆盖 {coverage:g}% · 未覆盖 {unclassified_n} 条")}'
        f'<div class="tsub">本期不展示负面主题图，避免把少数已归并记录误当作整体结构。待补规则高频观点：'
        f'{esc(unclassified_top)}；'
        '请在 Excel 的观点分布与原文中复核后确认新增规则。</div></div>'
    )
    if nonnegative_theme_note:
        shape_html += f'<div class="tsub" style="margin-top:7px">{esc(nonnegative_theme_note)}</div>'

    # 外溢
    spill_bar = bar_rows([(k, v) for k, v, _ in m6['l2'][:6]], m6['l2'][0][1] if m6['l2'] else 1, 'red')
    # 原声只承担证据作用：整份海报最多两条，避免售后区与原文区重复堆叠。
    # samples 现为三元组 (vp, text, 情感档)；旧版二元组按无情感处理。
    # 全貌模式（正面 ≥10 条）配额为「负面/中性 1 + 正面 1」，否则取前 2 条。
    def _sample_emo(item):
        return item[2] if len(item) >= 3 and item[2] else ''
    def _sample_ref(item):
        return item[3] if len(item) >= 4 and item[3] else ''
    def _sample_sig(item):
        # 同一原文只能展示一次；同一来源只有一条文本，因而也不会重复出现。
        return C.quote_key(str(item[1] or ''))
    quote_candidates = list(m8.get('samples') or [])
    if not quote_candidates:
        quote_candidates = [(f'命中「{kw}」', seg, '') for kw, seg in (m8.get('intel') or [])]
    if show_full:
        picked, seen = [], set()
        for want in ('负面', '中性', '正面'):
            for item in quote_candidates:
                body = str(item[1] or '')
                sig = _sample_sig(item)
                if not body or sig in seen or _sample_emo(item) != want:
                    continue
                seen.add(sig)
                picked.append(item)
                break
            if len(picked) == 2:
                break
        quote_rows = [(it[0], it[1], _sample_emo(it), _sample_ref(it)) for it in picked]
    else:
        quote_rows, quote_seen = [], set()
        for item in quote_candidates:
            body = str(item[1] or '')
            signature = _sample_sig(item)
            if not body or signature in quote_seen:
                continue
            quote_seen.add(signature)
            quote_rows.append((item[0], body, _sample_emo(item), _sample_ref(item)))
            if len(quote_rows) == 2:
                break
    samples_html = ''.join(
        (f'<div class="qt" style="border-left-color:{GOOD_GREEN}">'
         f'<b style="color:{GOOD_GREEN}">好评原声 · {esc(t)}</b>{esc(x)}</div>'
         if e == '正面' else
         f'<div class="qt"><b>客户原声 · {esc(t)}</b>{esc(x)}</div>')
        for t, x, e, _ in quote_rows)
    quote_more = max(0, len(quote_candidates) - len(quote_rows))
    quotes_more_html = (f'<div class="more">另有 {quote_more} 条代表性原声，见明细 Excel</div>'
                        if quote_more else '')

    # 口碑亮点区块（正面 ≥10 条才渲染；数据驱动，不足时口径说明已标注）
    praise_html = ''
    if show_full and m2.get('vp_top_pos'):
        vp_pos = m2['vp_top_pos']
        pos_bar = bar_rows([(r[0], r[1]) for r in vp_pos[:5]], vp_pos[0][1] or 1, 'green')
        used_quotes = {_sample_sig((t, x, e, ref)) for t, x, e, ref in quote_rows}
        pos_quote = next(
            ((it[0], it[1]) for it in quote_candidates
             if _sample_emo(it) == '正面' and _sample_sig(it) not in used_quotes),
            None,
        )
        pos_quote_html = ''
        if pos_quote:
            pos_quote_html = (f'<div class="qt" style="border-left-color:{GOOD_GREEN};margin-top:10px">'
                              f'<b style="color:{GOOD_GREEN}">好评原声 · {esc(pos_quote[0])}</b>'
                              f'{esc(pos_quote[1])}</div>')
        praise_html = (f'<div class="sec">'
                       f'{sec("praise", "口碑亮点", f"正面 {pos_n} 条 · 客户在夸什么")}'
                       f'{pos_bar}{pos_quote_html}</div>')

    # 集中度
    focus_blocks = ''
    for k in ('大区', '渠道', '专营店'):
        if m7.get(k):
            mx = m7[k][0][1] or 1
            focus_blocks += (f'<div class="fblk"><div class="fh">按{k}</div>' +
                             bar_rows([(a, b) for a, b in m7[k][:6]], mx) + '</div>')
    missing_note = ('字段缺失未执行：' + '、'.join(m7['missing'])) if m7.get('missing') else ''

    caveat_html = ''.join(f'<div class="cav">• {esc(x)}</div>' for x in M.get('caveats', []))

    # ---------- m9 · 关键洞察与建议动作 ----------
    m9 = S.get('m9') or {}
    insights = m9.get('insights') or []
    actions = m9.get('actions') or []
    summary = m9.get('summary') or ''
    panorama = M.get('analysis_mode') == 'vehicle_panorama'
    rank_title = '问题域排行' if panorama else '观点排行'
    rank_items = (m4.get('domain_top') or []) if panorama else (m4.get('vp_top') or [])

    LEVEL_COLOR = {'red': '#E64340', 'amber': '#F5820B', 'info': '#C9C0B4', 'good': GOOD_GREEN}
    PRIO_COLOR = {'P0': '#E64340', 'P1': '#F5820B', 'P2': '#8C8C8C'}

    # 区块 ③ 决策摘要
    summary_html = ''
    if insights or summary:
        cnt = {'P0': 0, 'P1': 0, 'P2': 0}
        for it in insights:
            cnt[it.get('priority', 'P2')] = cnt.get(it.get('priority', 'P2'), 0) + 1
        cells = ''.join(
            f'<div class="sc{"" if cnt.get(p) else " off"}">'
            f'<b style="color:{PRIO_COLOR[p]}">{cnt.get(p, 0)}</b><i>{p} 项</i></div>'
            for p in ('P0', 'P1', 'P2'))
        summary_html = (f'<div class="sec"><div class="sum">'
                        f'<div class="st">{esc(summary)}</div>'
                        f'<div class="sc">{cells}</div>'
                        f'</div></div>')

    # 区块 ⑧ 关键洞察卡（截断时保底保留 1 条 good，口碑亮点不因排序被挤掉）
    MAX_INS = 6
    shown_ins = insights[:MAX_INS]
    if len(insights) > MAX_INS:
        rest_good = [x for x in insights[MAX_INS:] if x.get('level') == 'good']
        if rest_good and not any(x.get('level') == 'good' for x in shown_ins):
            shown_ins = shown_ins[:-1] + [rest_good[0]]
    ins_cards = ''
    for it in shown_ins:
        lv = it.get('level', 'info')
        pg = it.get('priority', 'P2')
        bar = LEVEL_COLOR.get(lv, LEVEL_COLOR['info'])
        # good 洞察的徽章跟 level 色走（绿），避免 P1 橙徽章与绿条打架；其余按优先级
        pcolor = bar if lv == 'good' else PRIO_COLOR.get(pg, PRIO_COLOR['P2'])
        ev = [x for x in (it.get('evidence') or []) if x][:2]
        ev_html = ''.join(f'<div class="ev">· {esc(x)}</div>' for x in ev)
        rt = it.get('root') or ''
        rt_html = f'<div class="rt"><b>待验证方向</b> {esc(rt)}</div>' if rt else ''
        ins_cards += (f'<div class="ick">'
                      f'<div class="bar" style="background:{bar}"></div>'
                      f'<div class="body">'
                      f'<div class="h"><span class="pg" style="background:{pcolor}">{esc(pg)}</span>'
                      f'<span class="kd">{esc(it.get("kind", ""))}</span></div>'
                      f'<div class="cn">{esc(it.get("title", ""))}</div>'
                      f'{ev_html}{rt_html}'
                      f'</div></div>')
    ins_more = (f'<div class="more">另有 {len(insights) - MAX_INS} 条次要洞察，见明细 Excel</div>'
                if len(insights) > MAX_INS else '')
    insights_html = ''
    if ins_cards:
        insights_html = (f'<div class="sec">{sec("m9", "关键洞察", f"来自 {len(insights)} 条判据命中")}'
                         f'{ins_cards}{ins_more}</div>')

    # 区块 ⑨ 建议动作
    act_rows = ''
    for ac in actions[:MAX_INS]:
        pg = ac.get('priority', 'P2')
        ow = ac.get('owner') or ''
        act_rows += (f'<div class="act">'
                     f'<div class="ap" style="background:{PRIO_COLOR.get(pg, PRIO_COLOR["P2"])}">{esc(pg)}</div>'
                     f'<div><div class="ab">{esc(ac.get("action", ""))}</div>'
                     f'<div class="aw">{esc(ow)}</div>'
                     f'<div class="af">来自：{esc(ac.get("from", ""))}</div></div></div>')
    act_more = (f'<div class="more">另有 {len(actions) - MAX_INS} 项动作，见明细 Excel</div>'
                if len(actions) > MAX_INS else '')
    actions_html = ''
    if act_rows:
        actions_html = (f'<div class="sec">{sec("m9", "建议动作", "按优先级排序，可直接派活")}'
                        f'{act_rows}{act_more}</div>')

    # 公域区固定作为私域简报最末区块：未启用时也明确说明，避免把“无内容”误读为“未检索到”。
    if public.get('enabled'):
        cards = ''
        for item in (public.get('sources') or [])[:6]:
            title, url = item.get('title') or '公开来源', item.get('url') or ''
            meta = '｜'.join(x for x in (item.get('time_bucket'), item.get('source_type'), item.get('published_at')) if x)
            cards += (f'<div class="pub"><b>{esc(title)}</b><span>{esc(meta)}</span>'
                      f'<div>{esc(item.get("excerpt") or "")}</div><a href="{esc(url)}">查看原始来源</a></div>')
        empty = (f'公域证据未载入：{esc(public.get("reason"))}' if public.get('reason') else
                 '未检索到可核验公开证据。')
        public_body = cards or f'<div class="tsub">{empty}</div>'
        public_html = (f'<div class="public"><div class="sec">{sec("m8", "公域舆情观察", "外部链接证据，不计入私域统计")}'
                       f'<div class="tsub">检索：{esc(public.get("query") or "")}</div>{public_body}</div></div>')
    else:
        public_html = (f'<div class="public"><div class="sec">{sec("m8", "公域舆情观察", "外部链接证据，不计入私域统计")}'
                       '<div class="tsub">本期未启用公域检索；仅在用户明确要求时调用 WebSearch。</div></div></div>')

    H = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(topic)}专项简报</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","PingFang SC",system-ui,-apple-system,"Segoe UI",sans-serif;
background:#E9EBEF;color:#2B2B2B;line-height:1.5;-webkit-font-smoothing:antialiased;padding:22px 12px}}
.poster{{max-width:480px;margin:0 auto;background:#fff;border-radius:14px;overflow:hidden;
box-shadow:0 8px 34px rgba(60,40,10,.14)}}
.hd{{background:linear-gradient(155deg,#FFF3E2 0%,#FFFBF4 49%,#FFFFFF 100%);padding:22px 22px 18px;position:relative;min-height:250px;isolation:isolate;overflow:hidden}}
.hd:after{{content:"";position:absolute;inset:0;z-index:1;pointer-events:none;background:linear-gradient(90deg,rgba(255,255,255,.94) 0%,rgba(255,255,255,.88) 38%,rgba(255,255,255,.08) 62%,transparent 88%)}}
.hd .brand,.hd h1,.hd .period{{position:relative;z-index:2}}
.brand{{display:flex;align-items:center;gap:7px;font-size:11.5px;font-weight:700;color:#F5820B;letter-spacing:.6px}}
.brand i{{width:16px;height:16px;border-radius:4px;background:linear-gradient(135deg,#FFB347,#F5820B);display:inline-block}}
.hd h1{{font-size:28px;font-weight:800;letter-spacing:.5px;line-height:1.24;margin-top:14px;color:#F5820B;max-width:245px;overflow-wrap:anywhere}}
.hd h1 em{{display:block;font-style:normal;color:#2B2B2B}}
.period{{display:inline-block;margin-top:14px;border:1.6px solid #F5820B;border-radius:7px;
padding:4px 12px;font-size:13px;font-weight:700;color:#F5820B;background:#fff}}
.sec{{padding:0 22px;margin-top:20px}}
.t{{display:flex;align-items:center;gap:7px;font-size:15px;font-weight:800;color:#2B2B2B;margin-bottom:9px}}
.t i{{width:4px;height:15px;border-radius:2px;background:#F5820B;display:inline-block;flex:0 0 auto}}
.t .tt{{flex:1}}
.t span.sm{{font-size:10px;font-weight:400;color:#A8A8A8;text-align:right;line-height:1.3;flex:0 0 auto;max-width:52%}}
.tsub{{font-size:10.8px;color:#A8A8A8;margin:0 0 12px 12px;line-height:1.65}}
.total{{background:linear-gradient(135deg,#FFA53B 0%,#F5820B 55%,#EA7000 100%);border-radius:14px;
padding:18px 20px 16px;color:#fff;box-shadow:0 6px 20px var(--primary-shadow);position:relative;overflow:hidden}}
.total:after{{content:"";position:absolute;right:-40px;top:-60px;width:170px;height:170px;border-radius:50%;background:rgba(255,255,255,.1)}}
.total .tl{{display:flex;align-items:center;gap:9px;font-size:13.5px;font-weight:700;position:relative}}
.total .tl i{{width:22px;height:22px;border-radius:6px;background:rgba(255,255,255,.24);
display:flex;align-items:center;justify-content:center;font-size:13px;font-style:normal;font-weight:800}}
.total .tv{{font-size:38px;font-weight:800;letter-spacing:-.5px;line-height:1.1;margin-top:6px;
font-variant-numeric:tabular-nums;position:relative}}
.total .tv small{{font-size:15px;font-weight:600;margin-left:5px}}
.total .td{{font-size:10.5px;opacity:.88;margin-top:4px;position:relative}}
.split{{background:#fff;border-radius:11px;margin-top:13px;padding:13px 15px 14px;color:#2B2B2B}}
.srow{{display:grid;grid-template-columns:66px 62px 1fr;gap:8px;align-items:center;padding:8px 0 5px}}
.srow+.share{{border-top:1px dashed #F0E2CE}}
.sname{{font-size:13px;font-weight:700;color:#C4620A}}
.sname.red{{color:#E64340}}
.snum{{font-size:19px;font-weight:800;color:#2B2B2B;font-variant-numeric:tabular-nums;white-space:nowrap}}
.snum small{{font-size:10px;font-weight:400;color:#A8A8A8}}
.tags{{display:flex;flex-wrap:wrap;gap:5px;justify-content:flex-end}}
.tg{{font-size:10.5px;font-weight:700;color:#fff;background:#F5820B;border-radius:4px;padding:3px 7px;white-space:nowrap}}
.tg.red{{background:#E64340}}
.share{{display:grid;grid-template-columns:66px 62px 1fr;gap:8px;align-items:center;padding:0 0 8px}}
.share .sl{{font-size:10.5px;color:#A8A8A8}}
.share .sv{{font-size:12px;font-weight:800}}
.pctbar{{height:7px;border-radius:4px;background:#F5F0E9;overflow:hidden}}
.pctbar b{{display:block;height:100%;background:linear-gradient(90deg,#FFB347,#F5820B)}}
.pctbar b.red{{background:linear-gradient(90deg,#FF8A65,#E64340)}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.rrow{{display:grid;grid-template-columns:79px 1fr 28px;gap:6px;align-items:center;margin-bottom:7px}}
.rlab{{font-size:10px;color:#5A5A5A;text-align:right;line-height:1.25;white-space:nowrap;
overflow:hidden;text-overflow:ellipsis}}
.rbar{{background:#F7F2EA;border-radius:3px;height:14px;overflow:hidden}}
.rfill{{height:100%;border-radius:3px;background:linear-gradient(90deg,#FFCF8C,#F5820B)}}
.rval{{font-size:10.5px;font-weight:800;color:#C4620A;font-variant-numeric:tabular-nums;text-align:right}}
.dwrap{{display:flex;align-items:center;gap:8px}}
.lgrow{{display:flex;align-items:center;gap:5px;font-size:9.5px;color:#5A5A5A;margin-bottom:6px}}
.lgrow svg{{flex:0 0 auto}}
.lgn{{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.lgrow b{{color:#2B2B2B;font-variant-numeric:tabular-nums}}
.lgrow em{{font-style:normal;color:#A8A8A8;font-size:9px}}
.box{{background:#FFFBF4;border:1px solid #F7E7CF;border-radius:11px;padding:14px 16px}}
.ins{{background:#FFFBF4;border:1px solid #F7E7CF;border-radius:11px;padding:13px 15px;margin-bottom:10px}}
.ins .ih{{font-size:12.5px;font-weight:800;color:#C4620A;margin-bottom:5px;display:flex;gap:7px;align-items:center}}
.ins .ih em{{font-style:normal;font-size:10px;font-weight:700;color:#fff;background:#F5820B;
border-radius:4px;padding:2px 6px;flex:0 0 auto}}
.ins p{{font-size:11.5px;color:#5A5A5A;line-height:1.78}}
.qt{{background:#FAFAFA;border-left:3px solid #FFCF8C;border-radius:0 8px 8px 0;padding:9px 12px;
font-size:10.8px;color:#6A6A6A;line-height:1.72;margin-bottom:8px}}
.qt b{{color:#C4620A;display:block;margin-bottom:3px;font-size:10.5px}}
.fblk{{background:#FAFCFE;border-radius:10px;padding:12px 14px;margin-bottom:10px;border:1px solid #EAF2FA}}
.fh{{font-size:11px;font-weight:800;color:#1F4E79;margin-bottom:9px}}
.cav{{font-size:11.5px;color:#C00000;line-height:1.8}}
.act{{display:grid;grid-template-columns:42px 1fr;gap:11px;align-items:start;padding:11px 0}}
.act+.act{{border-top:1px dashed #F0E2CE}}
.act .ap{{font-size:10.5px;font-weight:800;color:#fff;border-radius:5px;padding:3px 0;text-align:center;
font-variant-numeric:tabular-nums}}
.act .ab{{font-size:11.5px;color:#2B2B2B;line-height:1.62}}
.act .aw{{font-size:10px;color:#A8A8A8;margin-top:3px}}
.act .af{{font-size:9.5px;color:#B9A88F;margin-top:2px}}
.sum{{background:#FFFBF4;border:1px solid #F7E7CF;border-radius:11px;padding:14px 16px}}
.sum .st{{font-size:12.5px;font-weight:800;color:#C4620A;line-height:1.7}}
.sum .sc{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:12px;
padding-top:11px;border-top:1px dashed #F0E2CE;text-align:center}}
.sum .sc.off{{opacity:.45}}
.sum .sc b{{display:block;font-size:20px;font-weight:800;line-height:1.1;font-variant-numeric:tabular-nums}}
.sum .sc i{{display:block;font-style:normal;font-size:9.5px;color:#A8A8A8;margin-top:3px}}
.ick{{display:grid;grid-template-columns:3px 1fr;border-radius:8px 11px 11px 0;overflow:hidden;
margin-bottom:10px}}
.ick .bar{{border-radius:0}}
.ick .body{{background:#FFFBF4;border:1px solid #F7E7CF;border-left:0;border-radius:0 11px 11px 0;
padding:12px 14px}}
.ick .h{{display:flex;align-items:center;gap:7px;margin-bottom:6px}}
.ick .pg{{font-size:10px;font-weight:800;color:#fff;border-radius:4px;padding:2px 6px;flex:0 0 auto;
font-variant-numeric:tabular-nums}}
.ick .kd{{font-size:9.5px;color:#A8A8A8}}
.ick .cn{{font-size:12px;font-weight:800;color:#2B2B2B;line-height:1.6}}
.ick .ev{{font-size:10.2px;color:#7A7A7A;line-height:1.68;margin-top:5px}}
.ick .rt{{font-size:10.2px;color:#5A5A5A;line-height:1.68;margin-top:4px}}
.ick .rt b{{color:#C4620A;font-weight:700}}
.more{{font-size:10px;color:#A8A8A8;text-align:center;padding:4px 0 2px}}
.note{{margin:18px 22px 0;background:#FAFAFA;border-radius:10px;padding:13px 15px;
font-size:10.2px;color:#9A9A9A;line-height:1.82}}
.note b{{color:#7A7A7A}}
.ft{{margin-top:18px;background:linear-gradient(180deg,#FFF7EC,#FFFDFA);padding:16px 22px 20px;text-align:center}}
.public{{margin-top:22px;padding:1px 0 20px;background:#F3F7FC;border-top:5px solid #5B7FA8}}
.pub{{background:#fff;border:1px solid #D9E5F2;border-radius:9px;padding:10px 12px;margin:8px 0;font-size:10.5px;color:#52606D;line-height:1.6}}
.pub b{{display:block;color:#294E73;font-size:11px}} .pub span{{display:block;color:#7B8A99;font-size:9.5px}} .pub a{{color:#276FB5;font-weight:700;text-decoration:none}}
.ft .fn{{font-size:12.5px;font-weight:800;color:#F5820B;letter-spacing:.4px;margin-bottom:5px}}
.ft .fl{{font-size:10.5px;color:#B9A88F;line-height:1.9}}
@media print{{@page{{size:504px 3600px;margin:0}}
body{{background:#fff;padding:0;width:504px;margin:0}}
.poster{{box-shadow:none;border-radius:0;max-width:504px}}
.sec,.ins,.act,.qt,.note{{break-inside:avoid}}}}
</style></head><body>
<div class="poster">

  <div class="hd">
    <div class="brand"><i></i>VOC 客户声音 · 数据分析</div>
    <h1>{esc(topic)}<em>专项简报</em></h1>
    <div class="period">{esc(header_period)}</div>
  </div>

  <div class="sec">
    <div class="total">
      <div class="tl"><i>!</i>{esc(topic)}声量</div>
      <div class="tv">{m2['n']:,}<small>条</small></div>
      <div class="td">口径 {esc(M['scope_desc']['main'])}｜范围 {esc(M['scope_desc']['target_model'])}｜
      渗透率万分之 {m2['penetration']:g}（{esc(m2['universe_label'])} {m2['universe']:,} 条中）</div>
    </div>
{split_html}
  </div>
{summary_html}

  <div class="sec">
    {sec('m5', f'声量与占比走势（{m5["unit"]}级，均值已归一）', '柱：周期均值<br>折线：占全量比（万分比）')}
    {trend_svg(m5['rows'])}
    <div style="display:flex;gap:4px;justify-content:space-between;margin:2px 6px 0;
    font-size:9.5px;color:#E64340;font-variant-numeric:tabular-nums">{trend_strip}</div>
    <div style="font-size:9px;color:#B9A88F;text-align:right;margin:2px 6px 0">各周期声量占全量比（万分比）</div>
  </div>
{baseline_html}
  <div class="sec">
    <div class="cols">
      <div>
        {sec('m4', rank_title)}
        {bar_rows(rank_items[:8], rank_items[0][1] if rank_items else 1)}
      </div>
      <div>
        {shape_html}
      </div>
    </div>
  </div>
{praise_html}

  <div class="sec">
    {sec('m6', '售后外溢结构', f"关键词直命中 {m6['spill_total']} 条中 {m6['service_total']} 条落服务侧")}
    {spill_bar}
  </div>
  <div class="sec">
    {sec('m7', '集中度分布', '按可用字段计算')}
    {focus_blocks}
    {f'<div class="tsub">{esc(missing_note)}</div>' if missing_note else ''}
  </div>
{insights_html}
{actions_html}

  <div class="sec">
    {sec('m8', '代表性客户原声', '仅展示 2 条；其余见明细 Excel')}
    {samples_html}{quotes_more_html}
  </div>
{public_html}

  <div class="note">
    <b>方法局限：</b>声量≠故障率，VOC 声量受客户活跃度、渠道触达与录入习惯影响；本报告用基线车型做归一化以部分抵消该偏差。
    统计结论为声量层面的相关性证据，不构成因果结论，根因需工程侧拆解验证。缺少 DMS 工单、返件检测与生产批次数据，无法确认失效机理与受影响批次范围。
  </div>

  <div class="ft">
    <div class="fn">数据来源：{esc(os.path.basename(M['data_file']))}</div>
    <div class="fl">{esc(M['period_name'])}｜生成于 {esc(M['generated_at'])}<br>
    配套明细见《{esc(topic)}专项简报_明细.xlsx》</div>
  </div>

</div></body></html>'''

    H = apply_theme(H, theme)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, 'w', encoding='utf-8').write(H)
    print(f'OK -> {a.out}  ({len(H):,} chars)｜视觉：{theme.get("name", theme_key)}')

if __name__ == '__main__':
    sys.exit(main())
