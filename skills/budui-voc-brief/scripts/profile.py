# -*- coding: utf-8 -*-
"""口径发现：把用户的自然语言主题，映射成数据里的标签口径。

输出 reports/profile.json，并打印人类可读的确认摘要。
容错：同义词表 + 拼音无关的编辑距离近似 + 疑似错拼提示。
"""
import sys, os, json, argparse, difflib, re, datetime
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
C.setup_stdout()

STOPWORDS = ['问题', '情况', '相关', '数据', '分析', '一下', '帮我', '做个', '做一份', '简报',
             '专项', '报告', '看看', '看下', '整理', '生成', '输出', '的', '了', '吗', '呢', '请', '吧', '我',
             'VOC', '客户声音', '声音', '反馈', '口碑']

def clean_query(q):
    s = q or ''
    for w in STOPWORDS:
        s = s.replace(w, '')
    return s.strip() or (q or '').strip()

def substrings(s, lo=2, hi=4):
    out = set()
    for n in range(lo, hi + 1):
        for i in range(len(s) - n + 1):
            out.add(s[i:i + n])
    return out

def ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()

def normalize_object_terms(query, lexicon):
    """先做受控词汇归一，再做标签发现；相关词只提出候选，绝不静默并入口径。"""
    q = query
    changes = []
    typo_hints = lexicon.get('typo_hints') or {}
    synonyms = lexicon.get('synonyms') or {}
    related = lexicon.get('related_candidates') or {}
    for typo, canonical in typo_hints.items():
        if typo and typo in q:
            q = q.replace(typo, canonical)
            changes.append({'input': typo, 'canonical': canonical, 'kind': '错别字已归一', 'requires_confirmation': False})
    for canonical, aliases in synonyms.items():
        for alias in aliases or []:
            if alias and alias in q and alias != canonical:
                q = q.replace(alias, canonical)
                changes.append({'input': alias, 'canonical': canonical, 'kind': '受控同义词已归一', 'requires_confirmation': False})
    for canonical, candidates in related.items():
        for candidate in candidates or []:
            if candidate and candidate in q:
                q = q.replace(candidate, canonical)
                changes.append({'input': candidate, 'canonical': canonical, 'kind': '相关词候选', 'requires_confirmation': True})
    return q, changes

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--query', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--topn', type=int, default=12)
    ap.add_argument('--target-model', help='用户已确认的目标车型；未传时尝试从 query 中识别')
    a = ap.parse_args()

    rows, F, cols = C.load_csv(a.data)
    total = len(rows)
    q_raw = a.query.strip()
    q = clean_query(q_raw)

    # ---- 基础统计 ----
    dates = [C.parse_date(C.G(r, F, 'date')) for r in rows]
    dates = [d for d in dates if d]
    latest_date = max(dates) if dates else None
    if latest_date:
        last_sunday = latest_date - datetime.timedelta(days=(latest_date.weekday() + 1) % 7)
        last_monday = last_sunday - datetime.timedelta(days=6)
        last_complete_week = {'start': last_monday.isoformat(), 'end': last_sunday.isoformat(),
                              'label': '最近完整自然周', 'data_cutoff': latest_date.isoformat()}
    else:
        last_complete_week = None
    models = Counter(C.G(r, F, 'model') for r in rows)
    model_field = F.get('model')
    INVALID_MODEL = ('无品牌', '无车型', '未知', '不详', '其他', '-')
    models_all = [{'model': m, 'rows': n} for m, n in models.most_common()]
    models_valid = [x for x in models_all
                    if x['model'] and not any(k in x['model'] for k in INVALID_MODEL)]
    available_models = {x['model'] for x in models_valid}
    requested_model = (a.target_model or '').strip()
    if requested_model and requested_model not in available_models:
        raise SystemExit(f'[车型不存在] {requested_model}；可选：{", ".join(sorted(available_models))}')
    # 车型只从车型列识别和过滤，绝不能作为标签/观点关键词参与口径匹配。
    mentioned_models = [m for m in available_models if m.lower() in q_raw.lower()]
    target_model = requested_model or (max(mentioned_models, key=len) if mentioned_models else '')
    if target_model:
        q = re.sub(re.escape(target_model), '', q, flags=re.IGNORECASE).strip()
    vehicle_panorama = bool(target_model and not q)
    if not q and not vehicle_panorama:
        raise SystemExit('[分析主题缺失] 识别并移除车型后未剩余标签主题，请补充对象或现象。')

    # ---- Step 0：意图与词汇归一 ----
    # “座椅声音”里的“声音”是用户要分析 VOC 的表达，不应被误当作“异响”现象。
    syn = C.load_json('assets/synonyms.json', {})
    q_before_lexicon = q
    q, lexical_changes = normalize_object_terms(q, syn)

    # ---- 标签词表 ----
    def label_counter(key, minlen=2):
        c = Counter(C.G(r, F, key) for r in rows
                    if F.get(key) and (not target_model or C.G(r, F, 'model') == target_model))
        return {k: v for k, v in c.items() if k and k not in ('-',) and len(k) >= minlen}

    l2c = label_counter('l2')
    l4c = label_counter('l4')
    l3c = label_counter('l3')
    vpc = label_counter('vp', 1)
    l2v, l4v, l3v, vpv = set(l2c), set(l4c), set(l3c), set(vpc)

    parts = substrings(q)

    def match(vals, counts):
        """评分以「与主题整体的相似度」为主，条数只作次级排序，
        避免只共享一个通用词（如"异响"）的无关标签挤占前排。"""
        out = []
        for v in vals:
            r = ratio(q, v)
            if v == q:
                sc, kind = 1.0, '精确'
            elif v in q:
                sc, kind = 0.90 + 0.10 * r, '标签是主题的一部分'
            elif any(p in v for p in parts):
                sc, kind = 0.30 + 0.60 * r, '主题片段命中'
            elif r >= 0.55:
                sc, kind = 0.60 * r, f'相似度 {r:.2f}'
            else:
                continue
            out.append({'value': v, 'rows': counts[v], 'score': round(sc, 3), 'match': kind,
                        'sim': round(r, 3)})
        out.sort(key=lambda x: (-x['score'], -x['rows']))
        return out[:a.topn]

    obj_cands = [dict(x, level='二级标签') for x in match(l2v, l2c)]
    obj_cands += [dict(x, level='四级标签') for x in match(l4v, l4c)]
    obj_cands += [dict(x, level='三级标签') for x in match(l3v, l3c)]
    obj_cands += [dict(x, level='观点标签') for x in match(vpv, vpc)]
    obj_cands.sort(key=lambda x: (-x['score'], -x['rows']))
    obj_cands = obj_cands[:a.topn]
    phe_cands = match(vpv, vpc)

    # ---- 核心词（用于扩展与正文检索）----
    cores = []
    for c in obj_cands[:2]:
        if c['score'] >= 0.8:
            cores.append(c['value'])
    for c in phe_cands[:2]:
        if c['score'] >= 0.8:
            cores.append(c['value'])
    if not cores:
        cores = [q]

    # ---- 扩展：同义词 / 疑似错拼 / 近似标签 ----
    syn_map = syn.get('synonyms', {})
    typo_map = syn.get('typo_hints', {})

    # 预构建「结构化」检索文本（1~4级标签 + 观点标签），不纳入正文/摘要等自由文本，
    # 保证关键字永远取自固定的分类字段，口径稳定可复现。
    blobs = [C.tag_blob(r, F) for r in rows]

    def count_in_text(term):
        return sum(1 for b in blobs if term in b)

    # 先收集候选，再统一统计
    raw_terms = []
    for w in cores:
        for t in syn_map.get(w, []):
            if t != w:
                raw_terms.append((w, t, '同义词表'))
        for k, v in typo_map.items():
            if (v == w or k == w) and k != w:
                raw_terms.append((w, k, '疑似错拼'))
    # 近似标签：只取相似度最高的若干个，控制扫描次数
    near = []
    for w in cores:
        for v in list(l2v | l4v | l3v | vpv):
            if v == w or len(v) < 2 or w in v or v in w:
                continue
            rr = ratio(w, v)
            if rr >= 0.6:
                near.append((rr, w, v))
    near.sort(reverse=True)
    for rr, w, v in near[:12]:
        raw_terms.append((w, v, f'近似标签({rr:.2f})'))

    expanded = []
    for w, t, src in raw_terms:
        n = count_in_text(t)
        if n > 0:
            expanded.append({'base': w, 'term': t, 'rows': n, 'source': src})
    seen, exp2 = set(), []
    for e in sorted(expanded, key=lambda x: -x['rows']):
        k = (e['base'], e['term'])
        if k in seen:
            continue
        seen.add(k)
        exp2.append(e)
    expanded = exp2[:20]

    # ---- 正文关键词命中 ----
    terms = sorted({c['value'] for c in obj_cands[:3]} | {c['value'] for c in phe_cands[:3]} | set(cores))
    text_hits = [{'term': t, 'rows': count_in_text(t)} for t in terms]
    text_hits.sort(key=lambda x: -x['rows'])

    # ---- 建议口径 ----
    best_obj = obj_cands[0] if obj_cands else None
    # 现象条件：从主题里剥离对象词后的残余（"发动机异响" - "发动机" = "异响"）
    residue = ''
    if best_obj:
        residue = q.replace(best_obj['value'], '').strip()
    has_phenomenon = len(residue) >= 2

    # 主题只给对象、不给现象时（"座椅"/"轮胎"/"空调"），
    # 不得用一个候选现象把口径收窄，应走"对象全覆盖"口径。
    if has_phenomenon:
        phen_term = residue
        phen_source = 'residue'
    elif phe_cands and phe_cands[0].get('sim', 0) >= 0.999:
        # 现象候选与主题词完全同名时才可充当现象条件
        phen_term = phe_cands[0]['value']
        phen_source = 'exact'
    else:
        phen_term = ''
        phen_source = 'none'

    obj_level = (best_obj or {}).get('level', '')
    obj_key = 'tag_any'
    obj_val = (best_obj or {}).get('value', '')
    # 若所谓“现象词”已包含在对象词内（如「哨兵模式」与误拆出的「哨兵」），
    # 它不能再作为观点标签的附加过滤条件，否则既重复描述又会漏掉对象范围内的记录。
    if phen_term and obj_val and phen_term in obj_val:
        phen_term = ''
        phen_source = 'absorbed_by_object'

    def count_scope(key, val, phen):
        n = 0
        for r in rows:
            if target_model and C.G(r, F, 'model') != target_model:
                continue
            if key == 'tag_any' and val and val not in C.scope_tag_blob(r, F):
                continue
            if key not in ('tag_any', None) and val and C.G(r, F, key) != val:
                continue
            # 主关键词来自二/三/四级标签与观点标签；现象条件只在观点标签中匹配。
            if phen and phen not in C.G(r, F, 'vp'):
                continue
            n += 1
        return n

    def count_keyword_scope(obj_term, phen_term):
        """对象词与现象词同时出现（仅 1~4 级标签 + 规范观点），用于关键词兜底口径。"""
        n = 0
        for r in rows:
            if target_model and C.G(r, F, 'model') != target_model:
                continue
            if obj_term and obj_term not in C.scope_tag_blob(r, F):
                continue
            if phen_term and phen_term not in C.G(r, F, 'vp'):
                continue
            n += 1
        return n

    # 对象全覆盖口径：只按标签取对象，不叠加现象条件
    obj_all_rows = count_scope('tag_any', obj_val, '') if obj_val else None

    obj_all_emotion = Counter()
    obj_all_negative = 0
    if obj_val:
        for r in rows:
            if target_model and C.G(r, F, 'model') != target_model:
                continue
            if obj_val not in C.scope_tag_blob(r, F):
                continue
            # 确认卡必须和正式分析共用同一套情感归一，不能把中性/未识别误报成负面。
            emo = C.emo_class(C.G(r, F, 'emotion')) or '其他'
            obj_all_emotion[emo] += 1
            if emo == '负面':
                obj_all_negative += 1
    obj_all_pos = obj_all_emotion.get('正面', 0)

    main_rows = count_scope('tag_any', obj_val, phen_term) if obj_val else None
    # 备选口径：上一级标签
    alt_key = None
    alt_val = ''
    if alt_key and obj_key:
        sub = Counter(C.G(r, F, alt_key) for r in rows
                      if C.G(r, F, obj_key) == obj_val and C.G(r, F, alt_key))
        alt_val = sub.most_common(1)[0][0] if sub else ''
    alt_rows = count_scope(alt_key, alt_val, phen_term) if (alt_key and alt_val) else None
    # 关键词兜底口径
    kw_rows = count_keyword_scope(obj_val, phen_term) if obj_val else 0

    # 推荐口径：命中过窄时自动上推层级
    no_phenomenon = (phen_source == 'none')
    if no_phenomenon:
        # 只有对象没有现象 → 直接推荐对象全覆盖，不猜现象
        recommend = 'object_all'
    elif main_rows is None:
        recommend = 'keyword' if kw_rows else None
    elif main_rows >= 10:
        recommend = 'main'
    elif (alt_rows or 0) >= 10:
        recommend = 'alt'
    elif kw_rows > main_rows:
        recommend = 'keyword'
    else:
        recommend = 'main'

    profile = {
        'query_raw': q_raw, 'query_cleaned': q,
        'analysis_mode': 'vehicle_panorama' if vehicle_panorama else 'component_special',
        'intent': {
            'job': 'VOC 专项简报',
            'model_from_query': target_model,
            'object_query_before_lexicon': q_before_lexicon,
            'object_query_canonical': q,
            'lexical_changes': lexical_changes,
            'requires_lexical_confirmation': any(x['requires_confirmation'] for x in lexical_changes),
        },
        'data_file': os.path.abspath(a.data),
        'total_rows': total,
        'date_range': [min(dates).isoformat(), max(dates).isoformat()] if dates else [],
        'recommended_time_windows': {'last_complete_week': last_complete_week},
        'days': len({d.isoformat() for d in dates}),
        'fields': F,
        'model_field': model_field,
        'models_all': models_all,
        'models': models_valid,
        'target_model': target_model,
        'model_selection_required': len(models_valid) > 1 and not target_model,
        'object_candidates': obj_cands,
        'phenomenon_candidates': phe_cands,
        'cores': cores,
        'expanded_terms': expanded,
        'text_hits': text_hits,
        'suggested': {
            'object': best_obj, 'object_key': obj_key, 'object_value': obj_val,
            'main_scope': ({'key': None, 'terms': [], 'phenomenon': ''} if vehicle_panorama else
                           {'key': 'tag_any', 'terms': [obj_val] if obj_val else [], 'phenomenon': phen_term}),
            'phenomenon': phen_term, 'phenomenon_source': phen_source,
            'object_all_rows': obj_all_rows,
            'object_all_negative': obj_all_negative,
            'object_all_positive': obj_all_pos,
            'object_all_emotion': dict(obj_all_emotion),
            'main_rows': main_rows,
            'alt': {'key': alt_key, 'value': alt_val, 'rows': alt_rows},
            'keyword_rows': kw_rows,
            'recommend': recommend,
        },
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(profile, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    # ---- 人类可读摘要 ----
    P = print
    P('=' * 62)
    P(f'【口径发现】分析目标：{q_raw}')
    P('=' * 62)
    P(f'数据：{total:,} 条 | 区间 {profile["date_range"] and " ~ ".join(profile["date_range"])} | {profile["days"]} 天')
    if vehicle_panorama:
        P(f'分析模式：车型全景（车型列 = {target_model}，不按部件收窄）')
    if lexical_changes:
        P('意图归一：' + '；'.join(f'{x["input"]} → {x["canonical"]}（{x["kind"]}）' for x in lexical_changes))
        if profile['intent']['requires_lexical_confirmation']:
            P('注意：含相关词候选，必须由用户确认后才能纳入口径。')
    P(f'车型字段：{model_field}')
    P('车型分布：' + ' | '.join(f'{m["model"]} {m["rows"]:,}' for m in profile['models'][:6]))
    P('')
    P('① 对象候选（标签层）')
    for c in obj_cands[:6]:
        P(f'   [{c["level"]}] {c["value"]}  ····· {c["rows"]:,} 条  ({c["match"]})')
    if not obj_cands:
        P('   （无命中）')
    P('')
    P('② 现象候选（观点标签层）')
    for c in phe_cands[:8]:
        P(f'   {c["value"]}  ····· {c["rows"]:,} 条  ({c["match"]})')
    if not phe_cands:
        P('   （无命中）')
    P('')
    P('③ 结构字段命中（二/三/四级标签 + 观点标签）')
    for t in text_hits[:8]:
        P(f'   {t["term"]}  ····· {t["rows"]:,} 条')
    P('')
    P('④ 自动容错候选（待确认）')
    if expanded:
        for e in expanded[:12]:
            P(f'   {e["base"]} → {e["term"]} ({e["source"]})  {e["rows"]:,} 条')
    else:
        P('   （无）')
    P('')
    P('⑤ 建议定稿口径（← 推荐 为系统建议，最终由你确认）')
    s = profile['suggested']
    rec = s.get('recommend')
    lines = []
    if s.get('phenomenon_source') == 'none' and s['object']:
        # 只有对象没有现象：给"对象全覆盖"口径，不猜现象
        tot = s['object_all_rows'] or 0
        neg = s.get('object_all_negative') or 0
        pos = s.get('object_all_positive') or 0
        hint = ''
        if tot:
            hint = f'｜其中负面 {neg:,}（{neg/tot*100:.0f}%）、正面 {pos:,}（{pos/tot*100:.0f}%）'
        lines.append(('object_all', f'{s["object"]["level"]}="{s["object_value"]}"（对象全覆盖，不叠现象）{hint}',
                      s['object_all_rows']))
    if s['object'] and s['phenomenon']:
        lines.append(('main', f'{s["object"]["level"]}="{s["object_value"]}" 且 含"{s["phenomenon"]}"',
                      s['main_rows']))
    elif s['object'] and s.get('phenomenon_source') != 'none':
        lines.append(('main', f'{s["object"]["level"]}="{s["object_value"]}"', s['object']['rows']))
    if s['alt']['value']:
        cond = f' 且 含"{s["phenomenon"]}"' if s['phenomenon'] else ''
        lines.append(('alt', f'{s["alt"]["key"].upper()}="{s["alt"]["value"]}"{cond}',
                      s['alt']['rows']))
    if s['object_value'] and s['phenomenon']:
        lines.append(('keyword', f'正文/标签同时含"{s["object_value"]}"与"{s["phenomenon"]}"',
                      s['keyword_rows']))
    elif s['object_value']:
        lines.append(('keyword', f'正文含"{s["object_value"]}"', s['keyword_rows']))
    for k, desc, n in lines:
        mark = '   ← 推荐' if k == rec else ''
        P(f'   {k.upper():10} {desc}')
        P(f'              → {n:,} 条{mark}')
    if not lines:
        P('   （标签层无命中，需人工指定口径）')
    P('')
    P('⑥ 车型范围')
    if profile['model_selection_required']:
        P('   未指定车型：请先选择一个车型，或选择“全部车型”。')
    elif profile['target_model']:
        P(f'   已从需求识别目标车型：{profile["target_model"]}')
    if profile['models']:
        for m in profile['models'][:8]:
            P(f'   {m["model"]}  ····· {m["rows"]:,} 条')
    else:
        P('   （无有效车型值，将按全部车型且跳过基线对比模块）')
    P('')
    P(f'profile.json → {a.out}')

if __name__ == '__main__':
    main()
