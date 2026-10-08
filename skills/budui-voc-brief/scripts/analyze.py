# -*- coding: utf-8 -*-
"""跑 9 个分析模块 → stats.json

用法:
  python analyze.py --scope reports/scope.json --out reports/stats.json

m1～m8 是事实层，m9 是判断层（关键洞察与建议动作，规则引擎见 insight.py）。

scope.json 由「口径确认」环节产出，结构见 references/module-spec.md。
"""
import sys, os, json, argparse, datetime, re, hashlib
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import insight as I
C.setup_stdout()

# 默认互斥形态规则（优先级顺序，命中即停）—— 见 references/module-spec.md
DEFAULT_SHAPE_RULES = [
    ('异响类',  r'异响|响声|噪音|异音|杂音|咔|哒|嗡|轰|啸'),
    ('伸缩卡滞类', r'卡|滞|不顺|不回|涩|弹不出|弹不开|收不回|回缩|无法弹|无法收|弹不回'),
    ('开合失效类', r'打不开|开不了|关不上|关不严|无法关闭|无法打开'),
    ('失灵类',  r'失灵|失效|没反应|无反应|不工作|不管用'),
    ('损坏类',  r'坏|断|裂|碎|损|变形|凹陷'),
    ('脱落类',  r'脱落|掉落|掉了|松脱|脱开'),
    ('外观类',  r'划伤|划痕|掉漆|色差|毛刺|磨损'),
    ('间隙类',  r'缝隙|间隙|不平|不齐|错位|翘'),
    ('性能类',  r'慢|弱|不足|达不到|偏差'),
    ('咨询类',  r'咨询|询问|怎么|如何'),
    ('设计抱怨类', r'不满|建议优化|希望|设计|形式'),
]
DEFAULT_THEME_RULES = {
    '正面': [
        ('舒适体验', r'舒适|柔软|包裹|支撑|按摩|通风|加热'),
        ('功能好用', r'好用|方便|灵敏|顺畅|满意|喜欢'),
        ('外观质感', r'好看|美观|质感|高级'),
        ('稳定可靠', r'稳定|可靠|耐用|无异常'),
    ],
    '中性': [
        ('使用咨询', r'怎么|如何|请问|能否|是否|操作|使用'),
        ('维修服务咨询', r'维修|保养|配件|售后|处理'),
        ('功能配置咨询', r'功能|配置|开关|设置'),
    ],
}

PRODUCT_INTEL = r'改良品|改进件|通病|召回|统一方案|批次|投诉|车质网|懂车帝|媒体|曝光|设计缺陷|缺陷'
SERVICE_INTEL = r'承诺|未兑现|推诿|拖延|没人管|投诉|12315|客服|系统故障'
SERVICE_L1 = ('售后服务', '服务品质', '服务网络', '交付服务', '商城运营')

INVALID_MODEL = ('无品牌', '无车型', '未知', '不详', '其他')

def shape_of(vp, rules):
    for name, pat in rules:
        if re.search(pat, vp or ''):
            return name
    return '其他'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scope', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    scope = json.load(open(a.scope, encoding='utf-8'))
    data_file = scope['data_file']
    rows, F, cols = C.load_csv(data_file)

    # 主分析时间窗与趋势参照分离：主指标只用用户确认的区间，历史数据仅供趋势图参照。
    date_window = scope.get('analysis_date_range') or {}
    window_start = C.parse_date(str(date_window.get('start') or ''))
    window_end = C.parse_date(str(date_window.get('end') or ''))
    if (date_window.get('start') and not window_start) or (date_window.get('end') and not window_end):
        raise SystemExit('[时间范围错误] analysis_date_range 的 start/end 必须是 YYYY-MM-DD')
    if window_start and window_end and window_start > window_end:
        raise SystemExit('[时间范围错误] start 不能晚于 end')
    # “最近完整自然周”必须是数据截止日前最后一个完整周一至周日，不能把未结束本周当周报。
    source_dates = [C.parse_date(C.G(r, F, 'date')) for r in rows]
    source_dates = [d for d in source_dates if d]
    if date_window.get('label') == '最近完整自然周' and source_dates:
        latest = max(source_dates)
        last_sunday = latest - datetime.timedelta(days=(latest.weekday() + 1) % 7)
        expected_start = last_sunday - datetime.timedelta(days=6)
        if (window_start, window_end) != (expected_start, last_sunday):
            raise SystemExit('[周报时间窗错误] 最近完整自然周应为 '
                             f'{expected_start.isoformat()} ~ {last_sunday.isoformat()}（数据截止 {latest.isoformat()}）')
    analysis_rows = [r for r in rows if not (window_start or window_end) or
                     (C.parse_date(C.G(r, F, 'date')) and
                      (not window_start or C.parse_date(C.G(r, F, 'date')) >= window_start) and
                      (not window_end or C.parse_date(C.G(r, F, 'date')) <= window_end))]

    topic = scope.get('topic') or scope.get('query_raw') or '专项简报'
    period = scope.get('period', '周')
    pspec = C.PERIOD_SPEC.get(period, C.PERIOD_SPEC['周'])
    grain = pspec['grain']

    ms = scope.get('main_scope') or {}
    analysis_mode = scope.get('analysis_mode') or ('vehicle_panorama' if scope.get('vehicle_panorama') else 'component_special')
    key, val = ms.get('key'), ms.get('value')
    scope_terms = [str(x).strip() for x in (ms.get('terms') or []) if str(x).strip()]
    if key == 'tag_any' and not scope_terms and val:
        scope_terms = [str(val)]
    phen = (ms.get('phenomenon') or '').strip()
    # 防御性兜底：即使旧 scope 或外部编排误把对象词的一部分写成现象，
    # 也不得额外限制到观点标签，避免「哨兵模式」又被要求观点标签含「哨兵」。
    if phen and key == 'tag_any' and any(phen in term for term in scope_terms):
        phen = ''
    target_model = (scope.get('target_model') or '').strip()
    baseline_model = (scope.get('baseline_model') or '').strip()
    extra = [t for t in (scope.get('extra_terms') or []) if t]
    exclude = [t for t in (scope.get('exclude_terms') or []) if t]
    theme_rules = scope.get('theme_rules') or {}
    negative_rules = [(n, p) for n, p in (theme_rules.get('负面') or scope.get('shape_rules') or DEFAULT_SHAPE_RULES)]
    positive_rules = [(n, p) for n, p in (theme_rules.get('正面') or DEFAULT_THEME_RULES['正面'])]
    neutral_rules = [(n, p) for n, p in (theme_rules.get('中性') or DEFAULT_THEME_RULES['中性'])]

    def phen_hit(r):
        if not phen:
            return True
        terms = [phen] + extra
        # 现象是观点维度，不能与对象标签或车型混在同一个条件里。
        return any(t in C.G(r, F, 'vp') for t in terms)

    def object_hit(r):
        if key == 'tag_any':
            return bool(scope_terms) and any(t in C.scope_tag_blob(r, F) for t in scope_terms)
        return not (key and val) or C.G(r, F, key) == val

    def in_main(r):
        if not object_hit(r):
            return False
        if target_model and C.G(r, F, 'model') != target_model:
            return False
        if not phen_hit(r):
            return False
        vp = C.G(r, F, 'vp')
        if any(x in vp for x in exclude):
            return False
        return True

    def in_main_tagged(r):
        """仅按标签（不含正文命中），用于口径稳健性对照。"""
        if not object_hit(r):
            return False
        if target_model and C.G(r, F, 'model') != target_model:
            return False
        if phen and phen not in C.G(r, F, 'vp'):
            return False
        return True

    main_rows = [r for r in analysis_rows if in_main(r)]
    n_main = len(main_rows)
    caveats = []

    # ============ M1 数据体检 ============
    dates = [C.parse_date(C.G(r, F, 'date')) for r in analysis_rows]
    dates = [d for d in dates if d]
    dset = sorted({d for d in dates})
    uid_col = F.get('uid')
    if uid_col:
        uc = Counter(C.G(r, F, uid_col) for r in rows)
        dup = sum(1 for v in uc.values() if v > 1)
        dup_desc = f'唯一ID {len(uc):,}，重复 {dup} 个'
    else:
        dup = 0
        dup_desc = '无唯一ID字段，按行计'

    optional = {k: F.get(k) for k in ('vin', 'store', 'region', 'ccode', 'channel')}
    miss = {}
    for k, col in optional.items():
        if not col:
            miss[k] = '字段缺失'
            continue
        blank = sum(1 for r in main_rows if C.G(r, F, k) in ('', '-'))
        miss[k] = f'{blank}/{n_main}（{blank / n_main * 100:.1f}%）' if n_main else '—'

    m1 = {
        'total_rows': len(analysis_rows),
        'date_from': dset[0].isoformat() if dset else '',
        'date_to': dset[-1].isoformat() if dset else '',
        'days': len(dset),
        'dup_desc': dup_desc,
        'missing': miss,
    }

    # ============ M2 规模与渗透率 ============
    universe = [r for r in analysis_rows if (not target_model or C.G(r, F, 'model') == target_model)]
    n_uni = len(universe)
    emo_raw = Counter(C.G(r, F, 'emotion') for r in main_rows)
    # 情感归一（common.emo_class）：吸收「正向」「好评」等变体，三档率一律用归一值
    emo = Counter(C.emo_class(C.G(r, F, 'emotion')) for r in main_rows)
    n_neg, n_pos, n_neu = emo.get('负面', 0), emo.get('正面', 0), emo.get('中性', 0)
    pos_rows = [r for r in main_rows if C.emo_class(C.G(r, F, 'emotion')) == '正面']
    neu_rows = [r for r in main_rows if C.emo_class(C.G(r, F, 'emotion')) == '中性']
    vp_pos = Counter(C.G(r, F, 'vp') for r in pos_rows if C.G(r, F, 'vp'))
    vp_neu = Counter(C.G(r, F, 'vp') for r in neu_rows if C.G(r, F, 'vp'))
    m2 = {
        'n': n_main,
        'universe': n_uni,
        'universe_label': target_model or '全量',
        'penetration': round(n_main / n_uni * 10000, 1) if n_uni else 0,
        'emotion': dict(emo_raw),
        'emotion_class': dict(emo),
        'negative_rate': round(n_neg / n_main * 100, 1) if n_main else 0,
        'negative_n': n_neg,
        'positive_rate': round(n_pos / n_main * 100, 1) if n_main else 0,
        'positive_n': n_pos,
        'neutral_rate': round(n_neu / n_main * 100, 1) if n_main else 0,
        'neutral_n': n_neu,
        # 正面口碑排行（全貌呈现的数据源）：[观点标签, 条数, 占正面%]
        'vp_top_pos': [[k, v, round(v / n_pos * 100, 1)] for k, v in vp_pos.most_common(5)] if n_pos else [],
        # 中性声音保留原始观点标签，同时独立进入中性主题归并；不得借用负面风险主题。
        'vp_top_neu': [[k, v, round(v / n_neu * 100, 1)] for k, v in vp_neu.most_common(5)] if n_neu else [],
        'robust_n': len([r for r in analysis_rows if in_main_tagged(r)]),
    }
    if n_main and n_pos < 10:
        caveats.append(f'正面 {n_pos} 条（{round(n_pos / n_main * 100, 1)}%），未达亮点呈现阈值，简报聚焦负面')
    if n_main < 30:
        caveats.append('样本量小（<30 条），结论仅供参考')

    # ============ M3 基线对比 ============
    m3 = None
    models_all = Counter(C.G(r, F, 'model') for r in rows)
    valid_models = [m for m, _ in models_all.most_common()
                    if m and not any(k in m for k in INVALID_MODEL)]
    if baseline_model:
        base_rows = [r for r in analysis_rows if C.G(r, F, 'model') == baseline_model]
        def hit_in(rs):
            return [r for r in rs if object_hit(r) and phen_hit(r)]
        tgt_rows = universe
        t_hit, b_hit = len(hit_in(tgt_rows)), len(hit_in(base_rows))
        t_rate = t_hit / len(tgt_rows) * 10000 if tgt_rows else 0
        b_rate = b_hit / len(base_rows) * 10000 if base_rows else 0
        multiple = round(t_rate / b_rate, 1) if b_rate else None
        base_gap = abs(len(tgt_rows) - len(base_rows)) / max(len(tgt_rows), len(base_rows), 1)
        m3 = {
            'target_label': target_model or '全量',
            'baseline_label': baseline_model,
            'target_n': t_hit, 'target_universe': len(tgt_rows), 'target_rate': round(t_rate, 1),
            'baseline_n': b_hit, 'baseline_universe': len(base_rows), 'baseline_rate': round(b_rate, 1),
            'multiple': multiple,
            'base_gap': round(base_gap * 100, 1),
        }
        if base_gap > 0.5:
            caveats.append(f'两车型声量基数差异 {base_gap * 100:.0f}%，倍数可比性下降，仅供参考')

    # ============ M4 观点主题归并 ============
    # 三种情感分别用各自规则归并，绝不跨情感混算；负面主题才可用于风险结论。
    vp_counter = Counter(C.G(r, F, 'vp') for r in main_rows if C.G(r, F, 'vp'))
    domain_counter = Counter(C.G(r, F, 'l2') for r in main_rows if C.G(r, F, 'l2'))
    neg_rows = [r for r in main_rows if C.emo_class(C.G(r, F, 'emotion')) == '负面']
    vp_neg = Counter(C.G(r, F, 'vp') for r in neg_rows if C.G(r, F, 'vp'))
    def theme_summary(emotion, emo_rows, rules):
        classified, unclassified = [], Counter()
        for row in emo_rows:
            vp = C.G(row, F, 'vp')
            theme = shape_of(vp, rules)
            if theme == '其他':
                unclassified[vp or '未标注观点'] += 1
            else:
                classified.append(theme)
        counter = Counter(classified)
        total, classified_n = len(emo_rows), sum(counter.values())
        unclassified_n = total - classified_n
        if classified_n + unclassified_n != total:
            raise SystemExit(f'[{emotion}观点主题归并自检失败] 已归并 {classified_n} + 未归并 {unclassified_n} ≠ {total}')
        return {
            'total': total, 'classified_n': classified_n, 'unclassified_n': unclassified_n,
            'coverage': round(classified_n / total * 100, 1) if total else 0,
            'exclusive': [[k, v, round(v / total * 100, 1)] for k, v in counter.most_common()] if total else [],
            'unclassified_vp_top': [[k, v] for k, v in unclassified.most_common(10)],
            'rule_review_required': bool(total and classified_n / total * 100 < 85.0),
        }

    pos_rows = [r for r in main_rows if C.emo_class(C.G(r, F, 'emotion')) == '正面']
    neu_rows = [r for r in main_rows if C.emo_class(C.G(r, F, 'emotion')) == '中性']
    themes = {
        '负面': theme_summary('负面', neg_rows, negative_rules),
        '正面': theme_summary('正面', pos_rows, positive_rules),
        '中性': theme_summary('中性', neu_rows, neutral_rules),
    }
    neg_theme = themes['负面']
    # 观点标签 × 情感交叉（top30，供 Excel ③ 表展示每个观点的正负构成）
    top30 = {k for k, _ in vp_counter.most_common(30)}
    vp_emo = defaultdict(Counter)
    for r in main_rows:
        vp = C.G(r, F, 'vp')
        if vp and vp in top30:
            vp_emo[vp][C.emo_class(C.G(r, F, 'emotion'))] += 1
    m4 = {
        # 兼容字段：仅负面主题用于风险结论和现有主题图；三档主题见 themes。
        'exclusive': ([] if analysis_mode == 'vehicle_panorama' else
                      neg_theme['exclusive']),
        'negative_n': n_neg,
        'classified_n': neg_theme['classified_n'],
        'shape_coverage': neg_theme['coverage'],
        'rule_review_required': neg_theme['rule_review_required'],
        'unclassified_n': neg_theme['unclassified_n'],
        'unclassified_vp_top': neg_theme['unclassified_vp_top'],
        'themes': themes,
        'vp_top': [[k, v] for k, v in vp_counter.most_common(30)],
        'vp_top_neg': [[k, v] for k, v in vp_neg.most_common(30)],
        'domain_top': [[k, v] for k, v in domain_counter.most_common(30)],
        'vp_emo': {k: dict(v) for k, v in vp_emo.items()},
    }

    # ============ M5 趋势（周期归一） ============
    win = pspec['trend_window']
    per_all, per_main, per_days = defaultdict(int), defaultdict(int), defaultdict(set)
    for r in rows:
        d = C.parse_date(C.G(r, F, 'date'))
        if not d:
            continue
        k = C.period_key(d, grain)
        per_all[k] += 1
        per_days[k].add(d.isoformat())
    # 历史趋势可使用主区间之外的同主题记录作参照；主指标仍严格只用 main_rows。
    for r in (r for r in rows if in_main(r)):
        d = C.parse_date(C.G(r, F, 'date'))
        if d:
            per_main[C.period_key(d, grain)] += 1
    keys = sorted(set(per_all) | set(per_main))
    trimmed = keys[-win:] if len(keys) > win else keys
    if len(keys) > win:
        caveats.append(f'数据覆盖 {len(keys)} 个{pspec["unit"]}，趋势图仅展示最近 {win} 个')
    trend_rows = []
    for k in trimmed:
        ds = per_days.get(k, set())
        nd = len(ds) or 1
        tot = per_all.get(k, 0)
        n = per_main.get(k, 0)
        rng = f'{min(ds)} ~ {max(ds)}' if ds else k
        trend_rows.append({
            'key': k, 'label': C.period_label(k, grain), 'from': min(ds) if ds else '',
            'to': max(ds) if ds else '', 'range': rng,
            'days': nd, 'total': tot, 'n': n,
            'avg': round(n / nd, 2), 'pct': round(n / tot * 10000, 1) if tot else 0,
        })
    m5 = {'unit': pspec['unit'], 'rows': trend_rows}

    # ============ M6 售后外溢 ============
    # 外溢必须先满足可复核的「直命中」关键词门槛。关联扩展是可选的第二层，
    # 不得和直命中混算，更不得因关键词为空而把同车型全部服务声音放进来。
    direct_terms = [str(t).strip() for t in (scope.get('spill_keywords') or []) if str(t).strip()]
    if not direct_terms:
        direct_terms = [t for t in (scope_terms + ([phen] if phen else [])) if t]
    direct_terms = list(dict.fromkeys(direct_terms))
    related_terms = [str(t).strip() for t in (scope.get('spill_related_terms') or []) if str(t).strip()]
    related_terms = [t for t in dict.fromkeys(related_terms) if t not in direct_terms]
    main_ids = {id(r) for r in main_rows}

    def spill_eligibility(r):
        # 与主口径同车型范围，否则会把其他车型的声音算进来
        if target_model and C.G(r, F, 'model') != target_model:
            return None
        if id(r) in main_ids:
            return None
        blob = C.text_blob(r, F)
        direct_hit = [t for t in direct_terms if t in blob]
        if direct_hit:
            return ('关键词直命中', direct_hit)
        related_hit = [t for t in related_terms if t in blob]
        if related_hit:
            return ('关联扩展（需确认）', related_hit)
        return None

    spill_entries = [(r, hit) for r in analysis_rows if (hit := spill_eligibility(r))]
    direct_entries = [(r, hit) for r, hit in spill_entries if hit[0] == '关键词直命中']
    related_entries = [(r, hit) for r, hit in spill_entries if hit[0] == '关联扩展（需确认）']
    # P0 防线：直命中记录必须能回指至少一个冻结关键词，任何不满足者中止而非静默放行。
    if any(not hit[1] for _, hit in direct_entries):
        raise SystemExit('[外溢口径错误] 发现无法回指直命中关键词的外溢记录。')
    spill = [r for r, _ in direct_entries]
    spill_svc = [r for r in spill if C.G(r, F, 'l1') in SERVICE_L1]
    l2c = Counter(C.G(r, F, 'l2') for r in spill_svc)
    l2_list = [[k, v, sum(1 for r in spill_svc if C.G(r, F, 'l2') == k and C.G(r, F, 'emotion') == '负面')]
               for k, v in l2c.most_common()]
    spill_pairs = []
    for r in spill_svc:
        if len(C.G(r, F, 'text')) > 60:
            spill_pairs.append((C.G(r, F, 'l2') or '服务侧', C.G(r, F, 'text')))
    m6 = {
        'spill_total': len(spill),
        'service_total': len(spill_svc),
        'related_total': len(related_entries),
        'related_service_total': sum(1 for r, _ in related_entries if C.G(r, F, 'l1') in SERVICE_L1),
        'contract': {
            'direct_terms': direct_terms,
            'related_terms': related_terms,
            'direct_logic': '同车型、同主分析时间窗、未归入主口径，且正文或结构化标签命中任一关键词',
            'related_logic': '同车型、同主分析时间窗、未归入主口径，且命中用户明确确认的关联词；不计入直命中外溢或其服务比值',
            'candidate_rows': len(analysis_rows),
            'after_main_exclusion': sum(1 for r in analysis_rows if (not target_model or C.G(r, F, 'model') == target_model) and id(r) not in main_ids),
        },
        'l2': l2_list,
        'quotes': [list(x) for x in C.dedup_quotes(spill_pairs, 5)],
        'ratio': round(len(spill_svc) / n_main, 2) if n_main else 0,
    }

    # ============ M7 集中度 ============
    m7 = {}
    if F.get('vin'):
        vin_rows = defaultdict(list)
        for r in main_rows:
            v = C.G(r, F, 'vin')
            if v and v != '-':
                vin_rows[v].append(r)
        repeats = {k: v for k, v in vin_rows.items() if len(v) > 1}
        m7['vin'] = {
            'valid': len(vin_rows), 'repeat': len(repeats),
            'rate': round(len(repeats) / len(vin_rows) * 100, 1) if vin_rows else 0,
            'detail': [[k, len(v), ' / '.join(sorted({C.G(x, F, 'vp') for x in v}))[:120]]
                       for k, v in sorted(repeats.items(), key=lambda x: -len(x[1]))[:15]],
        }
    for k, label in (('region', '大区'), ('channel', '渠道')):
        if F.get(k):
            c = Counter(C.G(r, F, k) for r in main_rows if C.G(r, F, k) not in ('', '-', '无区域信息'))
            m7[label] = [[a, b] for a, b in c.most_common(10)]
    if F.get('store'):
        c = Counter(C.G(r, F, 'store') for r in main_rows if C.G(r, F, 'store') not in ('', '-'))
        m7['专营店'] = [[a, b] for a, b in c.most_common(10)]
    m7['missing'] = [k for k in ('vin', 'region', 'channel', 'store') if not F.get(k)]

    # ============ M8 原文情报 ============
    intel_pat = PRODUCT_INTEL if scope.get('intel_type', 'product') == 'product' else SERVICE_INTEL
    intel = []
    for r in main_rows + spill:
        t = C.G(r, F, 'text')
        if not t:
            continue
        for m in re.finditer(intel_pat, t):
            s = max(0, m.start() - 45)
            seg = t[s:m.end() + 55].strip()
            intel.append((m.group(0), seg))
    intel_dedup = []
    seen = set()
    for kw, seg in intel:
        k = C.quote_key(seg)
        if k in seen:
            continue
        seen.add(k)
        intel_dedup.append([kw, C.clip(seg, 120)])
    # 原声带情感档（第三位），渲染层按「负面 1 + 正面 1」配额选取
    samples = [(C.G(r, F, 'vp'), C.G(r, F, 'text'), C.emo_class(C.G(r, F, 'emotion')), C.source_ref(r, F))
               for r in main_rows]
    m8 = {
        'intel': intel_dedup[:12],
        'samples': [list(x) for x in C.dedup_quotes(samples, 6)],
    }

    # ============ 明细行 ============
    det_fields = ['date', 'model', 'label_type', 'l1', 'l2', 'l3', 'l4', 'vp', 'emotion',
                  'channel', 'store', 'region', 'vin', 'ccode', 'uid', 'text']
    detail = [{**{k: C.G(r, F, k) for k in det_fields}, 'source_ref': C.source_ref(r, F)} for r in
              sorted(main_rows, key=lambda x: C.G(x, F, 'date'))]
    spill_fields = ['date', 'model', 'l1', 'l2', 'l3', 'l4', 'vp', 'emotion', 'store', 'text']
    spill_detail = [{
        'spill_class': hit[0], 'matched_terms': '／'.join(hit[1]),
        **{k: C.G(r, F, k) for k in spill_fields}, 'source_ref': C.source_ref(r, F)
    } for r, hit in sorted(spill_entries, key=lambda x: (x[1][0] != '关键词直命中', C.G(x[0], F, 'date')))]

    # ---- 主题图标 ----
    imap = C.load_json('assets/icon-map.json', {})
    # 封面不再按部件绘制：专项用通用 VOC 洞察视觉，车型全景用整车视觉。
    icon = 'icon-group-body.svg' if analysis_mode == 'vehicle_panorama' else imap.get('fallback', 'icon-generic.svg')

    object_desc = (f'车型全景（车型列 = "{target_model}"）' if analysis_mode == 'vehicle_panorama' else
                   ('二/三/四级标签/观点标签含「' + '／'.join(scope_terms) + '」' if key == 'tag_any' else f'{key.upper()}="{val}"'))
    scope_desc = {
        'main': object_desc + (f' 且 观点标签含"{phen}"' if phen else ''),
        'target_model': target_model or '全量',
        'baseline': baseline_model,
        'extra_terms': extra,
    }

    # m9 · 关键洞察与建议动作（从 m1～m8 的事实推导，不引入新数据）
    m9 = I.build(m1, m2, m3, m4, m5, m6, m7, m8, pspec['name'])

    # 公域仅在用户明确要求时启用；证据文件可为绝对路径或工作目录相对路径。
    public_query = ' '.join(x for x in (target_model, topic, window_start.isoformat() if window_start else '',
                                          window_end.isoformat() if window_end else '') if x)
    public = {'enabled': bool(scope.get('include_public')), 'query': public_query, 'sources': []}
    public_file = scope.get('public_evidence_file')
    if public.get('enabled') and public_file:
        candidates = [public_file] if os.path.isabs(public_file) else [
            os.path.abspath(public_file),
            os.path.join(os.path.dirname(os.path.abspath(a.scope)), os.path.basename(public_file)),
        ]
        found = next((p for p in candidates if os.path.isfile(p)), None)
        if not found:
            public['status'] = 'evidence_file_missing'
            public['reason'] = f'未找到公域证据文件：{public_file}'
        else:
            try:
                public = json.load(open(found, encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as exc:
                public = {'enabled': True, 'query': public_query, 'sources': [], 'status': 'evidence_file_invalid', 'reason': str(exc)}
        public['enabled'] = True
        public.setdefault('query', public_query)
        public['sources'] = [x for x in (public.get('sources') or [])
                             if isinstance(x, dict) and str(x.get('url') or '').startswith(('http://', 'https://'))]

    stats = {
        'meta': {
            'topic': topic,
            'query_raw': scope.get('query_raw', topic),
            # 用户可传 preset key、中文名或别名；最终解析和兜底在 render_poster.py，
            # 保证旧 scope/stats 没有该字段时仍沿用默认「琥珀晨曦」。
            'visual_theme': scope.get('visual_theme') or scope.get('theme') or '',
            'period': period, 'period_name': pspec['name'],
            'analysis_date_range': {
                'start': window_start.isoformat() if window_start else m1['date_from'],
                'end': window_end.isoformat() if window_end else m1['date_to'],
                'label': date_window.get('label') or ('专项（全量）' if not (window_start or window_end) else '统计区间'),
            },
            'analysis_mode': analysis_mode,
            'grain': grain, 'unit': pspec['unit'],
            'date_from': m1['date_from'], 'date_to': m1['date_to'], 'days': m1['days'],
            'total_rows': len(analysis_rows),
            'scope_desc': scope_desc,
            'caveats': caveats,
            'data_file': os.path.abspath(data_file),
            'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
            'skill_version': C.package_version(),
        },
        'icon': icon,
        'm1': m1, 'm2': m2, 'm3': m3, 'm4': m4, 'm5': m5, 'm6': m6, 'm7': m7, 'm8': m8,
        'm9': m9,
        'public': public,
        'detail': detail,
        'spill_detail': spill_detail,
        'models_available': valid_models[:8],
        'trace': {
            'source_file_sha256': C.file_sha256(data_file),
            'source_rows': len(rows),
            'analysis_rows': len(analysis_rows),
            'analysis_date_range': {
                'start': window_start.isoformat() if window_start else '',
                'end': window_end.isoformat() if window_end else '',
                'label': date_window.get('label') or ('全部数据' if not (window_start or window_end) else ''),
            },
            'main_scope_rows': n_main,
            'scope_sha256': hashlib.sha256(json.dumps(scope, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest(),
            'row_locator': '声音ID（如有）+ CSV 行号；所有主口径与外溢明细均保留该定位。',
        },
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(stats, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    P = print
    P('=' * 62)
    P(f'【分析完成】{topic}｜{pspec["name"]}')
    P('=' * 62)
    P(f'口径：{scope_desc["main"]}｜车型：{scope_desc["target_model"]}')
    P(f'主口径声量：{n_main} 条（标签口径对照 {m2["robust_n"]} 条）｜渗透率 万分之 {m2["penetration"]}')
    P(f'情感分布：正面 {m2["positive_rate"]}%｜中性 {m2["neutral_rate"]}%｜负面 {m2["negative_rate"]}%')
    if m3:
        P(f'基线对比：{m3["target_label"]} {m3["target_rate"]} vs {m3["baseline_label"]} {m3["baseline_rate"]}'
          f' → {m3["multiple"]} 倍')
    P('负面主题归并：' + ' | '.join(f'{k} {v}条({p}%)' for k, v, p in m4['exclusive'][:6]))
    P('趋势：' + ' '.join(f'{r["label"]}={r["n"]}' for r in m5['rows']))
    P(f'外溢直命中：{m6["spill_total"]} 条，其中售后侧 {m6["service_total"]} 条（比值 {m6["ratio"]}）｜关键词：{("／".join(direct_terms) or "未配置，已禁用")}')
    P(f'集中度：' + ' | '.join(f'{k} {len(v)}项' for k, v in m7.items() if k != 'missing'))
    P(f'情报：{len(m8["intel"])} 条｜原声 {len(m8["samples"])} 条')
    P('')
    P('【关键洞察】' + m9['summary'])
    for it in m9['insights']:
        tag = {'red': '🔴', 'amber': '🟠', 'good': '🟢', 'info': '⚪'}.get(it['level'], '·')
        P(f'  {tag} [{it["priority"]}] {it["title"]}')
        P(f'      根因：{it["root"]}')
        P(f'      动作：{it["action"]}')
    if m9['actions']:
        P('')
        P('【建议动作】')
        for ac in m9['actions']:
            P(f'  {ac["priority"]}  {ac["action"]}（{ac["owner"]}）')
    if caveats:
        P('注意：' + '；'.join(caveats))
    P(f'stats.json → {a.out}')

if __name__ == '__main__':
    main()
