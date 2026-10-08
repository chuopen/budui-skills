# -*- coding: utf-8 -*-
"""m9 · 关键洞察与建议动作（规则引擎）

从 m1～m8 的事实里推导结论。**不引入新数据，只做判断。**

输出结构（每条洞察）:
  {
    'kind':     洞察类型（系统性缺陷/车型特有问题/设计缺陷/服务外溢/重复报修/趋势恶化/集中风险/样本不足/口碑优势/正面集中/中性咨询信号）
    'level':    'red' | 'amber' | 'info' | 'good'   → 决定卡片配色（good=口碑亮点，绿）
    'title':    一句话结论（含关键数字）
    'evidence': [引用的具体事实，可追溯]
    'root':     待验证方向（不构成因果结论）
    'action':   建议动作
    'priority': 'P0' | 'P1' | 'P2'
    'owner':    建议牵头方向
  }

判据阈值集中在本文件顶部，改阈值即改敏感度。
**所有结论必须能回指到 evidence**，禁止无依据的推断。
"""
SCRIPT_INTERFACE = "internal-module"

# ---------------- 判据阈值（改这里即调敏感度） ----------------

TH = {
    'neg_rate_systemic':   90.0,   # 负面率 ≥ 此值 → 系统性缺陷
    'neg_rate_high':       70.0,   # 负面率 ≥ 此值 → 负面为主
    'multiple_model':       5.0,   # 基线倍数 ≥ 此值 → 车型特有问题
    'multiple_notable':     3.0,   # 基线倍数 ≥ 此值 → 明显高于基线
    'spill_ratio':          0.50,  # 外溢/主口径 ≥ 此值 → 显著服务外溢
    'shape_dominant':      60.0,   # 单一形态占比 ≥ 此值 → 高度同质
    'shape_min_coverage':  85.0,   # 形态规则覆盖不足时，不输出同质性业务判断
    'repeat_rate':         20.0,   # VIN 重复率 ≥ 此值 → 重复报修风险
    'trend_up':            1.30,   # 末周/均值 ≥ 此值 → 上升
    'trend_down':          0.70,   # 末周/均值 ≤ 此值 → 下降
    'trend_min_points':       4,   # 少于 4 个点不做趋势判断
    'small_sample':          30,   # 主口径 < 此值 → 样本不足
    'concentration_top':   40.0,   # 头部单项占比 ≥ 此值 → 集中风险
    'pos_rate_good':       60.0,   # 正面率 ≥ 此值 → 口碑优势（good）
    'pos_shape_dominant':  50.0,   # 正面首位观点占比 ≥ 此值 → 正面集中（good）
    'neutral_signal_rate': 30.0,   # 中性率 ≥ 此值 → 中性咨询信号
    'pos_present_min':       10,   # 正面条数 < 此值 → 不出正面判据（样本太少不构成口碑结论）
}


def _pct(a, b):
    return (a / b * 100) if b else 0.0


def _emo_desc(m2):
    """把情感分布转成「负面 136 / 中性 6」这类人话，不吐原始 dict。"""
    emo = m2.get('emotion_class') or m2.get('emotion') or {}
    if not isinstance(emo, dict) or not emo:
        return ''
    parts = [f'{k} {v}' for k, v in sorted(emo.items(), key=lambda kv: -kv[1])]
    return ' / '.join(parts)


def build(m1, m2, m3, m4, m5, m6, m7, m8, period_name):
    """返回 {'insights': [...], 'actions': [...], 'summary': str}"""
    ins = []
    n = m2.get('n') or 0
    neg = m2.get('negative_rate') or 0
    pen = m2.get('penetration') or 0
    emo_desc = _emo_desc(m2)

    # ---- 0. 样本不足：先说清楚，后续判断降级 ----
    small = n < TH['small_sample']
    if small:
        ins.append({
            'kind': '样本不足', 'level': 'amber',
            'title': f'仅 {n} 条，结论方向可信、幅度不可外推',
            'evidence': [f'主口径 {n} 条', f'区间 {m1.get("date_from")} ~ {m1.get("date_to")}'],
            'root': '标签粒度与问题分散共同导致命中偏少',
            'action': '先按方向处理；如需定量结论，放宽口径或延长观察周期后再复核',
            'priority': 'P1', 'owner': '数据分析',
        })

    # ---- 1. 问题性质：负面率 ----
    if n and neg >= TH['neg_rate_systemic']:
        ins.append({
            'kind': '系统性缺陷', 'level': 'red',
            'title': f'负面率 {neg:.1f}%，属系统性缺陷而非个案',
            'evidence': [f'负面 {m2.get("negative_n")} / {n} 条',
                         f'情感分布 {emo_desc}' if emo_desc else ''],
            'root': '问题在同类部件上批量复现，指向设计或批次质量，而非单车偶发',
            'action': '按批次与生产日期切分定位问题集中段，评估是否需要专项召回或服务活动',
            'priority': 'P0', 'owner': '质量 / 供应商质量',
        })
    elif n and neg >= TH['neg_rate_high']:
        ins.append({
            'kind': '负面集中', 'level': 'amber',
            'title': f'负面率 {neg:.1f}%，以负面反馈为主',
            'evidence': [f'情感分布 {emo_desc}' if emo_desc else f'负面 {m2.get("negative_n")} / {n} 条'],
            'root': '存在明确不满，但尚未表现为全量性缺陷',
            'action': '纳入本期重点跟进，跟踪下一周期负面率变化',
            'priority': 'P1', 'owner': '质量',
        })

    # ---- 2. 车型特异性：基线倍数 ----
    if m3 and n:
        mult = m3.get('multiple') or 0
        if mult >= TH['multiple_model']:
            ins.append({
                'kind': '车型特有问题', 'level': 'red',
                'title': f'渗透率是{m3["baseline_label"]}的 {mult} 倍，属{m3["target_label"]}特有问题',
                'evidence': [f'{m3["target_label"]} 万分之 {m3["target_rate"]}',
                             f'{m3["baseline_label"]} 万分之 {m3["baseline_rate"]}',
                             f'基数 {m3["target_universe"]:,} vs {m3["baseline_universe"]:,}'],
                'root': '两车基数接近但声量差倍数，排除规模因素，指向该车型专属设计或供应商差异',
                'action': '优先在目标车型上定位零部件差异；同步确认基线车型是否可复用其方案',
                'priority': 'P0', 'owner': '产品 / 质量',
            })
        elif mult >= TH['multiple_notable']:
            ins.append({
                'kind': '高于基线', 'level': 'amber',
                'title': f'渗透率为{m3["baseline_label"]}的 {mult} 倍，明显偏高',
                'evidence': [f'{m3["target_label"]} 万分之 {m3["target_rate"]}',
                             f'{m3["baseline_label"]} 万分之 {m3["baseline_rate"]}'],
                'root': '可能与该车型配置率或使用场景相关',
                'action': '对比两车配置差异，确认是设计问题还是使用强度差异',
                'priority': 'P1', 'owner': '产品',
            })

    # ---- 3. 负面风险主题集中度 ----
    # “其他”及未归并项不属于业务主题，也不能作为主题集中证据。
    excl = m4.get('exclusive') or []
    shape_coverage = m4.get('shape_coverage', 0)
    neg_n = m4.get('negative_n', m2.get('negative_n', 0))
    if excl and neg_n and shape_coverage >= TH['shape_min_coverage']:
        top_name, top_n, top_p = excl[0][0], excl[0][1], excl[0][2]
        if top_p >= TH['shape_dominant']:
            vp_top = [v for v, _ in (m4.get('vp_top_neg') or [])[:3]]
            ins.append({
                'kind': '负面主题高度集中', 'level': 'red',
                'title': f'负面中 {top_p:.0f}% 为「{top_name}」，风险主题集中',
                'evidence': [f'{top_name} {top_n} 条（占负面 {top_p}%）',
                             '高频观点：' + '、'.join(vp_top) if vp_top else ''],
                'root': '同一种失效模式反复出现，通常是单一零件或单一工序的确定性问题',
                'action': f'围绕「{top_name}」直接定位到零件级，不必做大范围排查',
                'priority': 'P0', 'owner': '质量 / 工程',
            })
    elif neg_n and shape_coverage < TH['shape_min_coverage']:
        unclassified_n = m4.get('unclassified_n', neg_n)
        candidates = '、'.join(f'{x[0]}({x[1]})' for x in (m4.get('unclassified_vp_top') or [])[:3])
        ins.append({
            'kind': '负面主题规则待补', 'level': 'info',
            'title': f'负面主题规则仅覆盖 {shape_coverage:.1f}%（{m4.get("classified_n", 0)}/{neg_n}），暂不判断风险结构',
            'evidence': [f'未覆盖 {unclassified_n} 条（{100 - shape_coverage:.1f}%）',
                         f'待审计高频观点：{candidates}' if candidates else '待审计高频观点：无'],
            'root': '现有规则与本期观点标签表达不匹配；这属于主题规则覆盖不足，不构成风险主题结论',
            'action': '复核未覆盖高频观点，确认新增、合并或排除规则后再生成负面主题图',
            'priority': 'P2', 'owner': 'VOC 运营 / 数据分析',
        })

    # ---- 4. 服务外溢 ----
    if m6:
        sp, sv, ratio = m6.get('spill_total') or 0, m6.get('service_total') or 0, m6.get('ratio') or 0
        if ratio >= TH['spill_ratio'] and sp:
            l2 = m6.get('l2') or []
            # l2 形如 [[名称, 条数, 占比], ...]
            top_l2 = '、'.join(f'{r[0]}({r[1]})' for r in l2[:3] if len(r) >= 2) if l2 else ''
            ins.append({
                'kind': '服务外溢', 'level': 'amber',
                'title': f'另有 {sp} 条相关声音未归入主问题，其中售后侧 {sv} 条',
                'evidence': [f'外溢 {sp} 条，售后侧 {sv} 条（比值 {ratio}）',
                             f'售后分布：{top_l2}' if top_l2 else ''],
                'root': '客户在处理该问题时产生了额外服务诉求，说明问题已向服务链条传导',
                'action': '同步告知售后准备话术与备件；若售后声量持续走高需评估主动服务方案',
                'priority': 'P1', 'owner': '售后 / 客户体验',
            })

    # ---- 5. 重复报修 ----
    vin = (m7 or {}).get('vin') or {}
    if isinstance(vin, dict) and vin.get('rate') is not None:
        if vin['rate'] >= TH['repeat_rate']:
            det = vin.get('detail') or []
            top_vin = det[0] if det else None
            ev = [f'可识别 VIN {vin.get("valid")} 台，其中 {vin.get("repeat")} 台重复报修（{vin.get("rate")}%）']
            if top_vin:
                ev.append(f'最高 {top_vin[0]} 报修 {top_vin[1]} 次')
            ins.append({
                'kind': '重复报修', 'level': 'red',
                'title': f'{vin["rate"]}% 的车辆重复报修，一次修复率偏低',
                'evidence': ev,
                'root': '首次维修未解决根本问题，指向诊断能力或维修方案有效性',
                'action': '抽取重复报修车辆做维修记录复盘，必要时升级技术支持介入',
                'priority': 'P0', 'owner': '售后技术',
            })

    # ---- 6. 趋势 ----
    trows = (m5 or {}).get('rows') or []
    if len(trows) >= TH['trend_min_points']:
        vals = [r['n'] for r in trows]
        avg = sum(vals) / len(vals)
        last = vals[-1]
        if avg > 0:
            r = last / avg
            if r >= TH['trend_up']:
                ins.append({
                    'kind': '趋势上升', 'level': 'amber',
                    'title': f'最新周期 {last} 条，为均值 {avg:.0f} 的 {r:.1f} 倍，声量在走高',
                    'evidence': [f'{period_name}序列 ' + ' '.join(f'{x["label"]}={x["n"]}' for x in trows)],
                    'root': '可能是问题扩散、也可能是传播效应放大，需结合绝对量判断',
                    'action': '提高观察频次，下个周期复核是否延续；若延续则升级处理级别',
                    'priority': 'P1', 'owner': '质量',
                })
            elif r <= TH['trend_down']:
                ins.append({
                    'kind': '趋势回落', 'level': 'info',
                    'title': f'最新周期 {last} 条，降至均值 {avg:.0f} 的 {r:.1f} 倍',
                    'evidence': [' '.join(f'{x["label"]}={x["n"]}' for x in trows)],
                    'root': '若期间有措施落地，可能已见效；否则需确认是否只是上报波动',
                    'action': '确认期间是否有对应改进措施，据此判断是否可收缩跟进力度',
                    'priority': 'P2', 'owner': '质量',
                })
    # 峰值提示：单周期异常突出
    if len(trows) >= TH['trend_min_points']:
        vals = [r['n'] for r in trows]
        avg = sum(vals) / len(vals)
        pk = max(trows, key=lambda x: x['n'])
        if avg > 0 and pk['n'] >= avg * 2 and pk['n'] >= 5:
            ins.append({
                'kind': '峰值异常', 'level': 'info',
                'title': f'{pk["label"]} 出现峰值 {pk["n"]} 条，为均值 {avg:.0f} 的 {pk["n"]/avg:.1f} 倍',
                'evidence': [f'峰值周期 {pk["label"]}', ' '.join(f'{x["label"]}={x["n"]}' for x in trows)],
                'root': '可能是集中投诉、批量反馈或一次事件引发的短期聚集',
                'action': '回看该周期原声确认是否与特定批次或事件相关',
                'priority': 'P2', 'owner': '质量',
            })

    # ---- 7. 集中度风险 ----
    # m7.<dim> 形如 [[值, 条数, 基数, 万分比], ...]；vin 为 dict
    for dim in ('大区', '渠道', '专营店'):
        det = (m7 or {}).get(dim)
        if not isinstance(det, list) or not det or not n:
            continue
        row = det[0]
        name, cnt = row[0], row[1]
        if not name or name == '-':
            continue
        share = _pct(cnt, n)
        if share >= TH['concentration_top']:
            ins.append({
                'kind': f'{dim}集中', 'level': 'amber',
                'title': f'{share:.0f}% 集中在「{name}」',
                'evidence': [f'{name} {cnt} 条 / 共 {n} 条',
                             f'该维度共 {len(det)} 项'],
                'root': '集中度过高既可能是真实问题聚集，也可能是该维度记录不完整导致的假集中',
                'action': f'先确认{dim}字段完整性；确认真实集中后再定向下探',
                'priority': 'P2', 'owner': '数据分析 / 区域',
            })
            break   # 只报最集中的一个维度，避免堆砌

    # ---- 8. 口碑优势 / 正面集中（全貌·正面判据，追加在风险判据之后） ----
    pos = m2.get('positive_rate') or 0
    n_pos = m2.get('positive_n') or 0
    vp_pos = m2.get('vp_top_pos') or []
    if n and n_pos >= TH['pos_present_min']:
        top_pos = '、'.join(str(r[0]) for r in vp_pos[:2] if r and r[0])
        if pos >= TH['pos_rate_good']:
            ins.append({
                'kind': '口碑优势', 'level': 'good',
                'title': f'正面率 {pos:.0f}%（{n_pos} 条），口碑是该主题的主导面',
                'evidence': [f'正面 {n_pos} / {n} 条',
                             f'高频好评点：{top_pos}' if top_pos else f'情感分布 {emo_desc}'],
                'root': '该对象的客户体验整体成立，负面是局部点而非基本面',
                'action': '把高频好评点沉淀为传播与销售话术素材，并保护对应体验不被后续改动破坏',
                'priority': 'P1', 'owner': '产品 / 市场',
            })
        elif vp_pos and vp_pos[0][2] >= TH['pos_shape_dominant']:
            ins.append({
                'kind': '正面集中', 'level': 'good',
                'title': f'好评中 {vp_pos[0][2]:.0f}% 集中在「{vp_pos[0][0]}」，客户在夸的是同一件事',
                'evidence': [f'{vp_pos[0][0]} {vp_pos[0][1]} 条（占正面 {vp_pos[0][2]}%）',
                             f'正面共 {n_pos} 条 / {n} 条'],
                'root': '该体验点形成了一致的正向认知，是可复用的口碑资产',
                'action': f'围绕「{vp_pos[0][0]}」提炼传播素材，并纳入产品定义的保留项',
                'priority': 'P1', 'owner': '产品 / 市场',
            })

    # ---- 9. 中性咨询信号（咨询/期望是产品机会，不是噪音） ----
    neu = m2.get('neutral_rate') or 0
    if n and neu >= TH['neutral_signal_rate']:
        ev = [f'中性 {m2.get("neutral_n")} / {n} 条（{neu:.1f}%）']
        vp_neu = m2.get('vp_top_neu') or []
        if vp_neu:
            ev.append(f'高频中性观点：{vp_neu[0][0]} {vp_neu[0][1]} 条')
        ins.append({
            'kind': '中性咨询信号', 'level': 'info',
            'title': f'中性占 {neu:.0f}%（{m2.get("neutral_n")} 条），客户在大量咨询而非抱怨',
            'evidence': ev,
            'root': '客户关注但认知未拉齐，咨询里通常藏着功能期望与改进建议',
            'action': '汇总高频咨询点交产品评估，可转化为 FAQ、功能引导或改进项',
            'priority': 'P2', 'owner': '产品',
        })

    # ---- 组装动作清单（按优先级） ----
    order = {'P0': 0, 'P1': 1, 'P2': 2}
    actions = []
    for it in sorted(ins, key=lambda x: order.get(x['priority'], 9)):
        actions.append({
            'priority': it['priority'],
            'action': it['action'],
            'owner': it['owner'],
            'from': it['kind'],
        })

    # 一句话总结·分区取 top：有风险洞察取最严重；全为 good/info 时取 good 头条（口碑导向）
    if ins:
        risk = [x for x in ins if x['level'] in ('red', 'amber')]
        if risk:
            top = sorted(risk, key=lambda x: (order.get(x['priority'], 9), x['level'] != 'red'))[0]
        else:
            good = [x for x in ins if x['level'] == 'good']
            top = good[0] if good else ins[0]
        summary = top['title']
    else:
        summary = f'本期 {n} 条，未触发风险判据，建议维持常规观察'

    if small:
        summary += '（样本量小，方向可信、幅度慎用）'

    return {'insights': ins, 'actions': actions, 'summary': summary}
