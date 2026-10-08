#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VOC 新车日报生成引擎。

用法:
  探测结构:  python generate_report.py inspect <excel路径> [--sheet 工作表名]
  生成日报:  python generate_report.py generate <excel路径> --date YYYY-MM-DD --series 车系
             [--sheet 工作表名] [--col 字段=列名,...] [--outdir 目录] [--title 标题]
             [--group-extra 车友群文本段，用 | 分隔]

仅依赖 openpyxl 与标准库。inspect 输出 JSON（车系清单、字段映射、缺失项），
generate 产出日报 HTML、导出 Excel 与 summary.json，并在 stdout 输出摘要 JSON。
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

try:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
except ImportError:
    print(json.dumps({"ok": False, "stage": "dependency",
                      "error": "缺少 openpyxl，请先执行: pip install openpyxl"}, ensure_ascii=False))
    sys.exit(2)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

EXCEL_EPOCH = dt.date(1899, 12, 30)
PLACEHOLDERS = {"", "-", "—", "–", "无", "空", "na", "n/a", "null", "none", "/", "未知", "#n/a"}
SENTI_ORDER = ["正面", "中性", "负面"]
SENTI_COLOR = {"正面": "#2e9e5b", "中性": "#8a94a6", "负面": "#d64545"}

# 字段识别候选：按顺序取第一个命中的列名（normalize 后精确相等优先，其次包含）。
FIELD_CANDIDATES = OrderedDict([
    ("date",      ["建单时间", "数据日期", "日期", "校验日期"]),
    ("series",    ["车系（人工修正）", "车系"]),
    ("sentiment", ["情感（人工修正）", "正负面（修正）", "正负面", "情感"]),
    ("labeltype", ["标签类型（人工修正）", "标签类别（修正）", "标签类型", "标签类别"]),
    ("opinion",   ["观点标签（人工修正）", "观点（补充）", "观点标签", "观点"]),
    ("level4",    ["四级标签（人工修正）", "四级分类（修正）", "四级标签", "四级分类"]),
    ("oneid",     ["OneID"]),
    ("vin",       ["VIN码", "VIN"]),
    ("serveno",   ["服务单号"]),
])
FIELD_LABEL = OrderedDict([
    ("date", "日期列"), ("series", "车系列"), ("sentiment", "情感列"), ("labeltype", "标签类型列"),
    ("opinion", "观点标签列"), ("level4", "四级标签列"), ("oneid", "OneID列"),
    ("vin", "VIN码列"), ("serveno", "服务单号列"),
])
REQUIRED_FIELDS = ["date", "sentiment", "labeltype", "opinion", "level4"]
SERIES_EXCLUDE = re.compile(r"基准|原始|码|类型|版本")
CN_PUNCT = str.maketrans("（）－０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
                         "()−0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")


def norm(s):
    return re.sub(r"\s+", "", str(s or "")).translate(CN_PUNCT)


def cell_str(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def parse_date(v):
    """兼容日期型单元格、Excel 序列号（含文本形态）、YYYY-MM-DD 等常见文本与全角数字。"""
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = cell_str(v).translate(CN_PUNCT)
    if not s:
        return None
    if re.fullmatch(r"\d{5}(\.0+)?", s):
        try:
            return EXCEL_EPOCH + dt.timedelta(days=int(float(s)))
        except (ValueError, OverflowError):
            return None
    m = re.search(r"(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})", s)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})(?:\d{4,6})?", s)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def classify_sentiment(v):
    s = norm(v)
    if not s:
        return None
    low = s.lower()
    if "正面" in s or s in ("正", "positive", "pos") or low == "positive":
        return "正面"
    if "负面" in s or s in ("负", "negative", "neg") or low == "negative":
        return "负面"
    if "中性" in s or s in ("中", "neutral") or low == "neutral":
        return "中性"
    return None


def valid_key(v):
    s = cell_str(v)
    if s.lower() in PLACEHOLDERS:
        return None
    return s


def read_sheet(ws):
    rows = ws.iter_rows(values_only=True)
    header = None
    data = []
    for row in rows:
        if header is None:
            non_empty = [c for c in row if c is not None and cell_str(c)]
            if len(non_empty) >= 3:
                header = list(row)
            continue
        if all(c is None or not cell_str(c) for c in row):
            continue
        data.append(list(row))
    return header or [], data


def score_header(header):
    """按字段候选命中情况给表头打分，返回 (得分, 映射)。"""
    names = [norm(h) for h in header]
    mapping, score = {}, 0.0
    for field, cands in FIELD_CANDIDATES.items():
        hit = None
        for cand in cands:
            c = norm(cand)
            for i, n in enumerate(names):
                if not n or i in mapping.values():
                    continue
                if n == c:
                    hit = (i, header[i], "exact")
                    break
            if hit:
                break
        if not hit:
            for cand in cands:
                c = norm(cand)
                if field == "series":
                    for i, n in enumerate(names):
                        if n and "车系" in n and not SERIES_EXCLUDE.search(n) and i not in mapping.values():
                            hit = (i, header[i], "contains")
                            break
                else:
                    for i, n in enumerate(names):
                        if n and c in n and i not in mapping.values():
                            hit = (i, header[i], "contains")
                            break
                if hit:
                    break
        if hit:
            mapping[field] = hit[0]
            score += 2.0 if field in REQUIRED_FIELDS else (1.0 if field == "series" else 0.5)
    return score, mapping


def pick_sheet(wb, forced=None):
    candidates = []
    for ws in wb.worksheets:
        rows = ws.iter_rows(min_row=1, max_row=3, values_only=True)
        header = next(rows, None) or []
        if len([c for c in header if c is not None and cell_str(c)]) < 5:
            continue
        score, mapping = score_header(header)
        if score > 0:
            candidates.append({"name": ws.title, "score": score, "state": ws.sheet_state,
                               "rows": ws.max_row, "mapping": mapping})
    if forced:
        chosen = [c for c in candidates if c["name"] == forced]
        if not chosen:
            raise SystemExit(json.dumps({"ok": False, "stage": "sheet",
                                         "error": f"工作表「{forced}」不是有效候选，候选: {[c['name'] for c in candidates]}"},
                                        ensure_ascii=False))
        return chosen[0], candidates
    if not candidates:
        raise SystemExit(json.dumps({"ok": False, "stage": "sheet",
                                     "error": "未找到具备 VOC 明细结构特征（日期/情感/标签/观点列）的工作表"},
                                    ensure_ascii=False))
    visible = [c for c in candidates if c["state"] == "visible"]
    pool = visible or candidates
    pool.sort(key=lambda c: (-c["score"], -c["rows"]))
    if not visible:
        pool[0]["note"] = "该表为隐藏工作表：可见表中无结构匹配，已自动回退"
    return pool[0], candidates


def resolve_columns(header, mapping, overrides):
    """overrides: dict 字段中文名 -> 列名。返回 field -> (idx, 列名)；缺失必需字段时阻断。"""
    names = [norm(h) for h in header]
    cn2field = {"日期": "date", "车系": "series", "情感": "sentiment", "标签类型": "labeltype",
                "观点": "opinion", "四级标签": "level4", "OneID": "oneid", "VIN": "vin", "服务单号": "serveno"}
    result = {}
    for field, idx in mapping.items():
        result[field] = (idx, header[idx])
    for cn, colname in (overrides or {}).items():
        field = cn2field.get(cn) or cn
        target = norm(colname)
        idx = next((i for i, n in enumerate(names) if n == target), None)
        if idx is None:
            idx = next((i for i, n in enumerate(names) if n and target in n), None)
        if idx is None:
            raise SystemExit(json.dumps({"ok": False, "stage": "columns",
                                         "error": f"覆盖列失败：找不到列「{colname}」"},
                                        ensure_ascii=False))
        result[field] = (idx, header[idx])
    missing = [FIELD_LABEL[f] for f in REQUIRED_FIELDS if f not in result]
    if missing:
        raise SystemExit(json.dumps({"ok": False, "stage": "columns",
                                     "error": f"必需列识别失败: {missing}",
                                     "hint": "用 --col 日期=列名,情感=列名,... 手动指定后重试",
                                     "header": [str(h) for h in header if h is not None]},
                                    ensure_ascii=False))
    return result


def load_records(data, cols):
    """把原始行读成 dict 记录，日期解析失败单独计数。"""
    records, bad_dates = [], 0
    for row in data:
        d = parse_date(row[cols["date"][0]]) if len(row) > cols["date"][0] else None
        if d is None:
            bad_dates += 1
            continue
        def g(field):
            idx = cols.get(field, (None,))[0]
            return row[idx] if idx is not None and len(row) > idx else None
        records.append({
            "date": d,
            "series": cell_str(g("series")),
            "sentiment_raw": cell_str(g("sentiment")),
            "sentiment": classify_sentiment(g("sentiment")),
            "labeltype": cell_str(g("labeltype")) or "未标注侧别",
            "opinion": cell_str(g("opinion")),
            "level4": cell_str(g("level4")),
            "oneid": cell_str(g("oneid")),
            "vin": cell_str(g("vin")),
            "serveno": cell_str(g("serveno")),
            "_raw": row,
        })
    return records, bad_dates


def dedup_daily(records):
    """同一日期内三轮串行去重：OneID+观点+四级 → VIN(规范化)+观点+四级 → 服务单号+观点+四级。"""
    by_day = OrderedDict()
    for r in records:
        by_day.setdefault(r["date"], []).append(r)
    kept = []
    for day in sorted(by_day):
        rows = list(by_day[day])
        rounds = [("oneid", lambda r: valid_key(r["oneid"]), lambda v: v),
                  ("vin", lambda r: valid_key(r["vin"]), lambda v: v.strip().lower()),
                  ("serveno", lambda r: valid_key(r["serveno"]), lambda v: v)]
        for _name, getter, transformer in rounds:
            seen, nxt = {}, []
            for r in rows:
                k_raw = getter(r)
                if k_raw is None:
                    nxt.append(r)
                    continue
                k = (transformer(k_raw), r["opinion"], r["level4"])
                if k in seen:
                    continue
                seen[k] = True
                nxt.append(r)
            rows = nxt
        kept.extend(rows)
    return kept


def side_of(labeltype):
    s = norm(labeltype)
    if "产品" in s:
        return "产品侧"
    if "服务" in s:
        return "服务侧"
    return "其他"


def build_stats(kept, series, report_date, days_span):
    per_day = OrderedDict()
    for d in days_span:
        per_day[d] = {"正面": 0, "中性": 0, "负面": 0, "未识别": 0, "合计": 0, "用户量": 0}
    day_rows = OrderedDict()
    for r in kept:
        day_rows.setdefault(r["date"], []).append(r)
    for d, rows in sorted(day_rows.items()):
        slot = per_day.setdefault(d, {"正面": 0, "中性": 0, "负面": 0, "未识别": 0, "合计": 0, "用户量": 0})
        for r in rows:
            slot[r["sentiment"] or "未识别"] += 1
            slot["合计"] += 1
        slot["用户量"] = len({r["oneid"] for r in rows if valid_key(r["oneid"])})

    today_rows = day_rows.get(report_date, [])
    # 总览指标为报告日期当日口径；趋势与热门话题用报告周期累计。
    total = len(today_rows)
    senti = Counter(r["sentiment"] or "未识别" for r in today_rows)
    users = len({r["oneid"] for r in today_rows if valid_key(r["oneid"])})

    opinions = {"产品侧": {}, "服务侧": {}, "其他": {}}
    for r in today_rows:
        opinions.setdefault(side_of(r["labeltype"]), {}).setdefault(
            r["sentiment"] or "未识别", Counter())[r["opinion"] or "（空）"] += 1
    opinion_top = {}
    for side, by_senti in opinions.items():
        opinion_top[side] = {
            s: [{"label": lb, "count": n} for lb, n in c.most_common(5)]
            for s, c in by_senti.items() if s in SENTI_ORDER
        }

    topics = {"产品侧": Counter(), "服务侧": Counter(), "其他": Counter()}
    for r in kept:
        topics[side_of(r["labeltype"])][r["level4"] or "（空）"] += 1
    topic_rows = {}
    for side, counter in topics.items():
        items = []
        for label, count in counter.most_common(3):
            trend = Counter()
            for r in kept:
                if side_of(r["labeltype"]) == side and (r["level4"] or "（空）") == label:
                    trend[r["date"]] += 1
            series_pts = [(d, trend.get(d, 0)) for d in days_span]
            vals = [v for _, v in series_pts]
            peak_i, low_i = vals.index(max(vals)), vals.index(min(vals))
            items.append({"label": label, "count": count,
                          "trend": [[d.isoformat(), v] for d, v in series_pts],
                          "peak": {"date": series_pts[peak_i][0].isoformat(), "value": vals[peak_i]},
                          "low": {"date": series_pts[low_i][0].isoformat(), "value": vals[low_i]}})
        topic_rows[side] = items

    classified = sum(senti[s] for s in SENTI_ORDER)
    negative_ratio = (senti["负面"] / total) if total else 0.0
    return {
        "date": report_date.isoformat(),
        "series": series,
        "total": total,
        "users": users,
        "opinions_total": total,
        "sentiment": {s: senti.get(s, 0) for s in SENTI_ORDER},
        "unrecognized": senti.get("未识别", 0),
        "negative_ratio": round(negative_ratio, 4),
        "per_day": [[d.isoformat(), v] for d, v in per_day.items()],
        "opinion_top": opinion_top,
        "topics": topic_rows,
    }


def esc(s):
    return html.escape(str(s), quote=True)


def mmdd(d):
    return f"{d.month}/{d.day}"


def cn_day(iso):
    x = dt.date.fromisoformat(iso)
    return f"{x.month}月{x.day}日"


def svg_trend(per_day):
    """堆叠柱（正/中/负）+ 负面占比折线，静态 SVG，无外部依赖。"""
    W, H, PL, PR, PT, PB = 960, 340, 56, 56, 30, 46
    days = [(dt.date.fromisoformat(d), v) for d, v in per_day]
    n = len(days)
    if n == 0:
        return "<p class='muted'>无可用日期数据</p>"
    inner_w, inner_h = W - PL - PR, H - PT - PB
    max_total = max((v["合计"] for _, v in days), default=1) or 1
    y_max = max_total * 1.15
    slot = inner_w / n
    bar_w = max(min(slot * 0.52, 64), 6)
    parts = []
    for axis in (0, 0.25, 0.5, 0.75, 1.0):
        y = PT + inner_h * (1 - axis)
        parts.append(f"<line x1='{PL}' y1='{y:.1f}' x2='{W-PR}' y2='{y:.1f}' stroke='#eee6dc' stroke-width='1'/>"
                     f"<text x='{PL-8}' y='{y+4:.1f}' text-anchor='end' class='ax'>{int(y_max*axis)}</text>"
                     f"<text x='{W-PR+8}' y='{y+4:.1f}' class='ax'>{int(axis*100)}%</text>")
    line_pts = []
    for i, (d, v) in enumerate(days):
        cx = PL + slot * (i + 0.5)
        acc = 0.0
        for s in SENTI_ORDER:
            h = inner_h * (v[s] / y_max)
            if v[s] > 0:
                parts.append(f"<rect x='{cx-bar_w/2:.1f}' y='{PT+inner_h-acc-h:.1f}' width='{bar_w:.1f}' height='{h:.1f}' "
                             f"rx='2' fill='{SENTI_COLOR[s]}'/>")
            acc += h
        parts.append(f"<text x='{cx:.1f}' y='{H-PB+18}' text-anchor='middle' class='ax'>{mmdd(d)}</text>")
        if v["合计"] > 0:
            ratio = (v["负面"] / v["合计"])
            ly = PT + inner_h * (1 - ratio)
            line_pts.append((cx, ly))
            parts.append(f"<circle cx='{cx:.1f}' cy='{ly:.1f}' r='4' fill='#fff' stroke='#e8730c' stroke-width='2.5'/>"
                         f"<text x='{cx:.1f}' y='{ly-10:.1f}' text-anchor='middle' class='pct'>{ratio*100:.1f}%</text>")
    if len(line_pts) > 1:
        path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(line_pts))
        parts.append(f"<path d='{path}' fill='none' stroke='#e8730c' stroke-width='2.5'/>")
    legend = "".join(
        f"<span class='lg'><i style='background:{SENTI_COLOR[s]}'></i>{s}</span>" for s in SENTI_ORDER)
    legend += "<span class='lg'><i style='background:#fff;border:2.5px solid #e8730c;border-radius:50%;width:9px;height:9px'></i>每日负面占比</span>"
    return (f"<svg viewBox='0 0 {W} {H}' role='img' aria-label='每日VOC趋势'>{''.join(parts)}</svg>"
            f"<div class='legend'>{legend}</div>")


def svg_mini(points, peak, low):
    W, H, P = 220, 64, 6
    if len(points) < 2:
        return f"<span class='muted'>{esc(points[0][1] if points else 0)} 条</span>"
    vals = [v for _, v in points]
    mx = max(vals) or 1
    step = (W - 2 * P) / (len(points) - 1)
    pts = [(P + i * step, H - P - (H - 2 * P) * v / mx) for i, v in enumerate(vals)]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    dots = "".join(
        f"<circle cx='{x:.1f}' cy='{y:.1f}' r='2.6' fill='{'#d64545' if points[i][0] == peak['date'] else '#e8730c'}'/>"
        for i, (x, y) in enumerate(pts))
    return (f"<svg viewBox='0 0 {W} {H}' class='mini'>"
            f"<path d='{path}' fill='none' stroke='#e8730c' stroke-width='2'/>{dots}</svg>")


def render_html(stats, meta, title, group_extra):
    d = lambda iso: dt.date.fromisoformat(iso)
    cards = [
        ("VOC 总量", f"{stats['total']:,}", "三轮去重后"),
        ("用户量", f"{stats['users']:,}", "OneID 去重"),
        ("负面占比", f"{stats['negative_ratio']*100:.1f}%", f"分母含未识别 {stats['unrecognized']} 条"),
    ]
    cards_html = "".join(f"<div class='card'><b>{esc(k)}</b><strong>{esc(v)}</strong><span>{esc(sub)}</span></div>"
                         for k, v, sub in cards)
    senti_bar = "".join(
        f"<div class='sb'><span class='sb-h'><i style='background:{SENTI_COLOR[s]}'></i>{s}"
        f"<b>{stats['sentiment'][s]:,}</b><em>{(stats['sentiment'][s]/stats['total']*100 if stats['total'] else 0):.1f}%</em></span>"
        f"<div class='sb-t'><div class='sb-f' style='width:{(stats['sentiment'][s]/stats['total']*100 if stats['total'] else 0):.1f}%;background:{SENTI_COLOR[s]}'></div></div></div>"
        for s in SENTI_ORDER)
    if stats["unrecognized"]:
        senti_bar += (f"<p class='warn'>⚠ 有 {stats['unrecognized']} 条记录的情感原值无法归类"
                      f"（空白或不含正/中/负关键词），已单列计数，未并入正/中/负。</p>")

    trend = svg_trend(stats["per_day"])

    opinion_html = ""
    for side in ("产品侧", "服务侧"):
        blocks = ""
        for s in SENTI_ORDER:
            items = stats["opinion_top"].get(side, {}).get(s, [])
            mx = max((it["count"] for it in items), default=1) or 1
            rows = "".join(
                f"<li><span class='ol'>{esc(it['label'])}</span>"
                f"<span class='ot'><i style='width:{it['count']/mx*100:.0f}%'></i></span>"
                f"<b>{it['count']}</b></li>"
                for it in items) or "<li class='muted'>当日无数据</li>"
            blocks += f"<div class='op'><h5 style='color:{SENTI_COLOR[s]}'>{s} TOP5</h5><ul>{rows}</ul></div>"
        opinion_html += f"<section class='blk'><h4>{side}</h4><div class='ops'>{blocks}</div></section>"

    topic_html = ""
    for side in ("产品侧", "服务侧"):
        items = stats["topics"].get(side, [])
        rows = ""
        for it in items:
            pts = [(p, v) for p, v in it["trend"]]
            rows += (f"<tr><td>{esc(it['label'])}</td><td>{it['count']:,}</td>"
                     f"<td>{svg_mini(pts, it['peak'], it['low'])}</td>"
                     f"<td>峰 {cn_day(it['peak']['date'])} · {it['peak']['value']}<br>"
                     f"谷 {cn_day(it['low']['date'])} · {it['low']['value']}</td></tr>")
        rows = rows or "<tr><td colspan='4' class='muted'>无数据</td></tr>"
        topic_html += (f"<section class='blk'><h4>{side} · 按报告周期累计声量</h4>"
                       f"<table class='tt'><tr><th>四级标签</th><th>累计声量</th><th>逐日趋势</th><th>峰 / 谷</th></tr>{rows}</table></section>")

    group_html = ""
    if group_extra:
        lis = "".join(f"<li>{esc(x)}</li>" for x in group_extra.split("|") if x.strip())
        group_html = f"<h3>车友群动态</h3><div class='blk'><ul class='grp'>{lis}</ul></div>"

    per_day_rows = "".join(
        f"<tr><td>{esc(iso)}</td><td>{row['正面']}</td><td>{row['中性']}</td>"
        f"<td>{row['负面']}</td><td>{row['未识别']}</td><td>{row['合计']}</td>"
        f"<td>{row['用户量']}</td></tr>"
        for iso, row in stats["per_day"])
    per_day_table = (f"<h3>逐日明细</h3><div class='blk'><table><tr><th>日期</th><th>正面</th><th>中性</th>"
                     f"<th>负面</th><th>未识别</th><th>合计</th><th>用户量</th></tr>{per_day_rows}</table></div>")

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · {esc(stats['series'])} · {esc(stats['date'])}</title>
<style>
:root{{--ink:#2b2620;--muted:#8a8378;--line:#eee6dc;--accent:#e8730c;--surface:#fff;--bg:#f7f4ef}}
*{{box-sizing:border-box;margin:0}}
html{{background:var(--bg)}}
body{{font-family:"PingFang SC","Microsoft YaHei","Segoe UI",sans-serif;background:var(--bg);color:var(--ink);line-height:1.6;padding:32px 16px}}
main{{max-width:1040px;margin:0 auto}}
header.hero{{background:linear-gradient(120deg,#e8730c,#f0a04b);color:#fff;border-radius:16px;padding:30px 34px;margin-bottom:22px}}
header.hero h1{{font-size:26px;letter-spacing:1px}}
header.hero p{{opacity:.92;margin-top:6px;font-size:14px}}
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:22px}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:16px 20px}}
.card b{{display:block;font-size:13px;color:var(--muted);font-weight:500}}
.card strong{{font-size:28px;color:var(--accent);font-variant-numeric:tabular-nums}}
.card span{{display:block;font-size:12px;color:var(--muted)}}
h3{{font-size:17px;margin:26px 0 10px}}
.blk{{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px 22px;margin-bottom:14px}}
.blk h4{{font-size:15px;margin-bottom:10px;color:#6b5638}}
section.trend{{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px 14px 10px}}
svg{{width:100%;height:auto}}
.ax{{font-size:11px;fill:#a39a8c}}
.pct{{font-size:11px;fill:#6b3200;font-weight:600;paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}}
.legend{{display:flex;gap:16px;justify-content:center;padding:6px 0 8px;font-size:12px;color:var(--muted)}}
.lg{{display:inline-flex;align-items:center;gap:5px}}
.lg i{{width:11px;height:11px;border-radius:3px;display:inline-block}}
.sb{{margin:8px 0}}
.sb-h{{display:flex;align-items:center;gap:8px;font-size:13px}}
.sb-h b{{margin-left:auto}}
.sb-h em{{font-style:normal;color:var(--muted);min-width:56px;text-align:right}}
.sb-t{{height:9px;background:#f0ebe3;border-radius:6px;margin-top:5px;overflow:hidden}}
.sb-f{{height:100%;border-radius:6px}}
.warn{{background:#fdf3e7;border:1px solid #f3d9b8;border-radius:10px;padding:9px 14px;font-size:13px;color:#8a5a1e;margin-top:12px}}
.ops{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
.op ul{{list-style:none}}
.op li{{display:grid;grid-template-columns:minmax(96px,34%) 1fr 2.2em;align-items:center;gap:10px;padding:4px 0;font-size:13px}}
.ol{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.ot{{height:8px;background:#f0ebe3;border-radius:5px;overflow:hidden}}
.ot i{{display:block;height:100%;background:linear-gradient(90deg,#f0a04b,#e8730c);border-radius:5px}}
.op li b{{text-align:right;font-variant-numeric:tabular-nums}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{color:var(--muted);font-weight:500;font-size:12px}}
.mini{{width:200px}}
.grp li{{margin:6px 0}}
.meta{{font-size:12.5px;color:var(--muted)}}
.meta b{{color:var(--ink);font-weight:600}}
details{{margin-top:8px}}
summary{{cursor:pointer;color:var(--accent)}}
footer{{text-align:center;color:var(--muted);font-size:12px;margin-top:30px}}
@media(max-width:720px){{.cards{{grid-template-columns:1fr 1fr}}.ops{{grid-template-columns:1fr}}}}
</style></head><body><main>
<header class="hero"><h1>{esc(title)} · {esc(stats['series'])}</h1>
<p>报告日期 {esc(stats['date'])}　|　数据周期 {esc(stats['per_day'][0][0])} 至 {esc(stats['per_day'][-1][0])}　|　仅统计车系「{esc(stats['series'])}」</p></header>
<div class="cards">{cards_html}</div>
<h3>当日情感结构</h3><div class="blk">{senti_bar}</div>
<h3>每日 VOC 趋势</h3><section class="trend">{trend}</section>
<h3>当日观点榜</h3>{opinion_html}
<h3>热门话题 TOP3</h3>{topic_html}
{per_day_table}
{group_html}
<h3>数据来源与识别口径</h3><div class="blk meta">
<p><b>文件</b>：{esc(meta['file'])}　<b>工作表</b>：{esc(meta['sheet'])}</p>
<p><b>报告日期</b>：{esc(stats['date'])}　<b>日期列</b>：{esc(meta['columns'].get('日期列',''))}（取日部分）</p>
<p><b>车系筛选</b>：{esc(meta['columns'].get('车系列','(未识别车系列)'))} =「{esc(stats['series'])}」，仅统计该车系</p>
<p><b>参与统计</b>：车系命中 {meta['series_hits']:,} 行 → 周期去重后 {meta['period_kept']:,} 条，其中报告日期当日 {stats['total']:,} 条；解析失败日期 {meta['bad_dates']} 行（未计入）</p>
<p><b>去重口径</b>：同一日期内三轮串行去重，每轮保留组内第一条 —— ①OneID＋观点标签＋四级标签；②VIN码（去空格转小写）＋观点标签＋四级标签；③服务单号＋观点标签＋四级标签；占位符视为无效，按日去重、不跨日合并。页面与导出 Excel 同口径。</p>
<details><summary>查看识别字段与口径明细</summary><p style="margin-top:8px">{'　'.join(f"{esc(k)}「{esc(v)}」" for k, v in meta['columns'].items())}</p>
<p>情感原值含「正/中/负」关键词归类，其余单列为未识别；热门话题即人工修正四级标签；观点榜按标签类型分产品侧/服务侧。</p></details></div>
<footer>由 budui-voc-daily 生成 · {esc(dt.date.today().isoformat())}</footer>
</main></body></html>"""


def export_excel(stats, records, cols, meta, path):
    from openpyxl import Workbook
    wb = Workbook()
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="C96A1B")

    def style_header(ws):
        for c in ws[1]:
            if c.value is not None:
                c.font, c.fill = head_font, head_fill
                c.alignment = Alignment(vertical="center")
        ws.freeze_panes = "A2"

    ws = wb.active
    ws.title = "总览"
    ws.append(["项目", "数值"])
    info = [
        ("文件名", meta["file"]), ("工作表", meta["sheet"]),
        ("报告日期", stats["date"]), ("车系筛选", f"{meta['columns'].get('车系列','(未识别)')} = {stats['series']}"),
        ("日期列", meta["columns"].get("日期列", "")), ("车系命中行数", meta["series_hits"]),
        ("周期去重后记录数", meta.get("period_kept", "")),
        ("当日去重后记录数", stats["total"]), ("用户量（OneID去重）", stats["users"]),
        ("观点量（同当日VOC总量口径）", stats["opinions_total"]),
        ("未识别情感", stats["unrecognized"]), ("负面占比（小数）", stats["negative_ratio"]),
        ("去重口径", "同一日期内三轮串行：①OneID+观点+四级；②VIN(规范化)+观点+四级；③服务单号+观点+四级"),
    ] + [(f"识别·{k}", v) for k, v in meta["columns"].items()]
    for row in info:
        ws.append(list(row))
    ws.append([])
    ws.append(["逐日", "正面", "中性", "负面", "未识别", "合计", "用户量"])
    for iso, row in stats["per_day"]:
        ws.append([iso, row["正面"], row["中性"], row["负面"],
                   row["未识别"], row["合计"], row["用户量"]])
    style_header(ws)

    ws = wb.create_sheet("观点")
    ws.append(["侧别", "情感", "排名", "观点标签", "数量"])
    r = 0
    for side in ("产品侧", "服务侧"):
        for s in SENTI_ORDER:
            for i, it in enumerate(stats["opinion_top"].get(side, {}).get(s, []), 1):
                ws.append([side, s, i, it["label"], it["count"]])
                r += 1
    style_header(ws)

    ws = wb.create_sheet("热门话题")
    ws.append(["侧别", "排名", "四级标签", "累计声量", "峰值日期", "峰值", "谷值日期", "谷值"])
    for side in ("产品侧", "服务侧"):
        for i, it in enumerate(stats["topics"].get(side, []), 1):
            ws.append([side, i, it["label"], it["count"], it["peak"]["date"], it["peak"]["value"],
                       it["low"]["date"], it["low"]["value"]])
    style_header(ws)

    date_idx = cols["date"][0]
    keep_idx = [date_idx] + [i for i in range(len(cols["_header"])) if i != date_idx]
    out_header = [(str(cols["_header"][i]) if cols["_header"][i] is not None else f"列{i}")
                  for i in keep_idx]

    def first_col_datetime(v):
        if isinstance(v, dt.datetime):
            return v
        if isinstance(v, dt.date):
            return dt.datetime.combine(v, dt.time())
        p = parse_date(v)
        return dt.datetime.combine(p, dt.time()) if p else v

    ws = wb.create_sheet("负面VOC清单")
    ws.append(out_header)
    style_header(ws)
    for rec in records:
        if rec["sentiment"] == "负面" and rec["date"].isoformat() == stats["date"]:
            row = rec["_raw"]
            vals = [row[i] if len(row) > i else None for i in keep_idx]
            vals[0] = first_col_datetime(vals[0])
            ws.append([vals[0]] + [cell_str(v) for v in vals[1:]])

    ws = wb.create_sheet("VOC明细")
    ws.append(out_header)
    style_header(ws)
    for rec in records:
        if rec["date"].isoformat() == stats["date"]:
            row = rec["_raw"]
            vals = [row[i] if len(row) > i else None for i in keep_idx]
            ws.append([first_col_datetime(vals[0])] + [cell_str(v) for v in vals[1:]])

    for name in ("负面VOC清单", "VOC明细"):
        sheet = wb[name]
        sheet.column_dimensions[sheet.cell(row=1, column=1).column_letter].width = 19
        for col_idx in range(2, min(sheet.max_column, 14) + 1):
            sheet.column_dimensions[sheet.cell(row=1, column=col_idx).column_letter].width = 14
        for r in range(2, sheet.max_row + 1):
            sheet.cell(row=r, column=1).number_format = "yyyy-mm-dd hh:mm:ss"
    wb.save(path)


def cmd_inspect(args):
    wb = openpyxl.load_workbook(args.excel, read_only=True, data_only=True)
    chosen, candidates = pick_sheet(wb, args.sheet)
    header, data = read_sheet(wb[chosen["name"]])
    score, mapping = score_header(header)
    cols_probe = {f: header[i] for f, i in mapping.items()}
    missing = [FIELD_LABEL[f] for f in REQUIRED_FIELDS if f not in mapping]
    series_counter = Counter()
    date_vals = set()
    if "series" in mapping:
        si = mapping["series"]
        for row in data:
            series_counter[cell_str(row[si]) if len(row) > si else ""] += 1
    if "date" in mapping:
        di = mapping["date"]
        for row in data:
            d = parse_date(row[di] if len(row) > di else None)
            if d:
                date_vals.add(d)
    payload = {
        "ok": True, "file": Path(args.excel).name, "rows": len(data),
        "sheet": chosen["name"], "sheet_score": score,
        "candidates": [{"name": c["name"], "score": c["score"], "rows": c["rows"]} for c in candidates],
        "columns": {FIELD_LABEL[f]: str(cols_probe[f]) for f in mapping},
        "missing_required": missing,
        "series_values": [{"series": s or "(空)", "count": n} for s, n in series_counter.most_common(30)],
        "date_range": [min(date_vals).isoformat(), max(date_vals).isoformat()] if date_vals else None,
        "next": ("确认「哪个车系算新车」与报告日期后执行 generate："
                 f"python generate_report.py generate <excel> --date YYYY-MM-DD --series 车系"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_generate(args):
    overrides = {}
    if args.col:
        for pair in args.col.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                overrides[k.strip()] = v.strip()
    wb = openpyxl.load_workbook(args.excel, read_only=True, data_only=True)
    chosen, _ = pick_sheet(wb, args.sheet)
    header, data = read_sheet(wb[chosen["name"]])
    _, mapping = score_header(header)
    cols = resolve_columns(header, mapping, overrides)
    cols["_header"] = header
    records, bad_dates = load_records(data, cols)

    if "series" not in cols:
        raise SystemExit(json.dumps({"ok": False, "stage": "series",
                                     "error": "该表未识别车系列，无法按车系筛选新车日报；可用 --col 车系=列名 指定"},
                                    ensure_ascii=False))
    si = cols["series"][0]
    series_hits = [r for r in records if r["series"] == args.series]
    if not series_hits:
        present = Counter(r["series"] for r in records).most_common(10)
        raise SystemExit(json.dumps({"ok": False, "stage": "series",
                                     "error": f"车系「{args.series}」无记录",
                                     "present": [{"series": s, "count": n} for s, n in present]},
                                    ensure_ascii=False))

    report_date = parse_date(args.date)
    if report_date is None:
        raise SystemExit(json.dumps({"ok": False, "stage": "date",
                                     "error": f"报告日期无法解析: {args.date}（需 YYYY-MM-DD）"},
                                    ensure_ascii=False))
    kept = dedup_daily(series_hits)
    days = sorted({r["date"] for r in kept})
    stats = build_stats(kept, args.series, report_date, days)
    if stats["total"] == 0:
        raise SystemExit(json.dumps({"ok": False, "stage": "data",
                                     "error": f"车系「{args.series}」在 {report_date} 前后无去重后数据",
                                     "available_days": [d.isoformat() for d in days[:20]]},
                                    ensure_ascii=False))

    meta = {"file": Path(args.excel).name, "sheet": chosen["name"],
            "columns": {FIELD_LABEL[f]: str(cols[f][1]) for f in cols if f != "_header"},
            "series_hits": len(series_hits), "bad_dates": bad_dates, "period_kept": len(kept)}

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    base = f"VOC新车日报_{args.series}_{report_date.isoformat()}"
    html_path = outdir / f"{base}.html"
    xlsx_path = outdir / f"{base}.xlsx"
    html_path.write_text(render_html(stats, meta, args.title, args.group_extra), encoding="utf-8")
    export_excel(stats, kept, cols, meta, xlsx_path)
    summary = {"ok": True, "html": str(html_path), "excel": str(xlsx_path),
               "stats": {k: stats[k] for k in ("date", "series", "total", "users", "sentiment",
                                               "unrecognized", "negative_ratio")}}
    if not args.no_png:
        png_path = outdir / f"{base}.png"
        png_result = render_png(html_path, png_path, est_height(stats, args.group_extra))
        if png_result is True:
            summary["png"] = str(png_path)
        else:
            summary["png"] = None
            summary["png_note"] = png_result
    (outdir / f"{base}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


PNG_SCALE = 2          # 2 倍采样，长图缩放/预览更清晰
PNG_VIEW_W = 1280      # 截图视口宽（CSS 像素）


def est_height(stats, group_extra):
    """按已知布局与实际行数估算整页像素高度，作截图视口高度。

    只是上限估计：乘 1.35 留足余量，多余空白由 render_png 的像素级底部裁剪
    （content_bottom）精确去掉，因此宁大勿小。
    """
    op_rows = sum(len(v) for side in stats["opinion_top"].values() for v in side.values())
    topic_rows = sum(len(v) for v in stats["topics"].values())
    h = 2702
    h += len(stats["per_day"]) * 34          # 逐日明细行
    h += (30 - op_rows) * 33                 # 观点榜不足 30 行（3 侧别组 × 5 行）时
    h += (6 - topic_rows) * 90               # 话题榜不足 6 行（2 侧 × 3 行）时
    if group_extra:
        h += 130
    if stats["unrecognized"]:
        h += 60
    return max(2400, min(int(h * 1.35), 30000))


def find_browser():
    """按常见安装位置查找可用的 Edge/Chrome 可执行文件（含用户级安装目录）。"""
    import os
    import shutil
    cands = []
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    cands += [rf"{pf}\Google\Chrome\Application\chrome.exe", rf"{pf86}\Google\Chrome\Application\chrome.exe",
              rf"{pf}\Microsoft\Edge\Application\msedge.exe", rf"{pf86}\Microsoft\Edge\Application\msedge.exe",
              rf"{local}\Google\Chrome\Application\chrome.exe", rf"{local}\Microsoft\Edge\Application\msedge.exe"]
    cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
              "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"]
    cands += [shutil.which(n) for n in ("chrome", "google-chrome", "chromium", "msedge")]
    return next((c for c in cands if c and Path(c).exists()), None)


def content_bottom(png, scale=PNG_SCALE):
    """检测非背景行的最大 y，用于精确裁掉截图底部空白；无 Pillow/numpy 时返回 None。"""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None
    im = Image.open(png).convert("RGB")
    a = np.array(im)
    bg = a[3, 3].astype(int)
    diff = np.abs(a.astype(int) - bg).sum(axis=2)
    rows = np.where((diff > 14).any(axis=1))[0]
    if not len(rows):
        return im.size[1]
    return min(int(rows.max()) + 16 * scale, im.size[1])


def render_png(html_path, png_path, height):
    """用无头 Edge/Chrome 把整页 HTML 截成高清 PNG 长图；失败返回说明文字，不阻断交付。

    方法（借鉴 budui-voc-brief）：按估算高度截大视口 + 2 倍采样，再用像素级
    非背景行检测裁掉底部空白——高度估准与否只影响裁剪量，不影响正确性。
    注意浏览器退出后截图文件可能延迟 1-2 秒落盘，必须轮询等待；首次失败时
    重建 profile 重试一次。
    """
    import shutil
    import subprocess
    import tempfile
    import time
    browser = find_browser()
    if not browser:
        return ("未找到 Edge/Chrome，无法自动出 PNG；可安装浏览器后重跑，"
                "或手动用浏览器打开 HTML 截图")
    uri = html_path.resolve().as_uri()
    profile = Path(tempfile.gettempdir()) / "voc-daily-browser-profile"

    def run(args, timeout):
        profile.mkdir(parents=True, exist_ok=True)
        return subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-first-run",
                               "--hide-scrollbars", f"--force-device-scale-factor={PNG_SCALE}",
                               f"--user-data-dir={profile}"]
                              + args, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)

    def wait_file(target, seconds=20):
        for _ in range(seconds * 2):
            if target.exists() and target.stat().st_size > 10000:
                return True
            time.sleep(0.5)
        return False

    def shot():
        png_path.unlink(missing_ok=True)
        raw = png_path.with_name("_raw_" + png_path.name)
        raw.unlink(missing_ok=True)
        proc = run([f"--window-size={PNG_VIEW_W},{height}", f"--screenshot={raw}", uri], 90)
        return proc, raw, wait_file(raw)

    def finish(raw):
        """裁掉底部空白后落盘为最终 PNG；无 Pillow 时原样改名。"""
        try:
            from PIL import Image
        except ImportError:
            raw.replace(png_path)
            return png_path.stat().st_size  # 无 Pillow，跳过裁剪原样交付
        bottom = content_bottom(str(raw))
        im = Image.open(raw)
        if bottom and bottom < im.size[1]:
            im = im.crop((0, 0, im.size[0], bottom))
        im.save(png_path, optimize=True)
        raw.unlink(missing_ok=True)
        return png_path.stat().st_size

    try:
        try:
            proc, raw, ok = shot()
        except subprocess.TimeoutExpired:
            return "浏览器截图超时，已跳过 PNG"
        if not ok:
            shutil.rmtree(profile, ignore_errors=True)
            try:
                proc, raw, ok = shot()
            except subprocess.TimeoutExpired:
                return "浏览器截图超时，已跳过 PNG"
        if ok:
            size = finish(raw)
            return True if size > 10000 else "截图内容异常偏小，已放弃 PNG"
        raw.unlink(missing_ok=True) if raw.exists() else None
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return "浏览器截图失败" + (f"：{detail[-1][:200]}" if detail else "")
    except OSError as exc:
        return f"浏览器启动失败：{exc}"


def main():
    p = argparse.ArgumentParser(description="VOC 新车日报生成引擎")
    sub = p.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("inspect", help="探测 Excel 结构：工作表、字段映射、车系清单、日期范围")
    pi.add_argument("excel")
    pi.add_argument("--sheet", help="指定工作表名（默认自动按结构特征选择）")
    pi.set_defaults(fn=cmd_inspect)
    pg = sub.add_parser("generate", help="生成日报 HTML 与导出 Excel")
    pg.add_argument("excel")
    pg.add_argument("--date", required=True, help="报告日期 YYYY-MM-DD")
    pg.add_argument("--series", required=True, help="新车车系（来自 inspect 的车系清单）")
    pg.add_argument("--sheet", help="指定工作表名")
    pg.add_argument("--col", help="手动指定列，如: 日期=建单时间,情感=正负面（修正）")
    pg.add_argument("--outdir", default="voc_daily_output", help="输出目录")
    pg.add_argument("--title", default="VOC 新车日报", help="日报标题")
    pg.add_argument("--group-extra", default="", help="车友群动态文本段，用 | 分隔")
    pg.add_argument("--no-png", action="store_true", help="跳过 PNG 长图输出")
    pg.set_defaults(fn=cmd_generate)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
