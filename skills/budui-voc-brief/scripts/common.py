# -*- coding: utf-8 -*-
"""budui-voc-brief 共用工具：字段识别、数据加载、文本处理。

列名不写死：按模糊规则识别，兼容"（人工修正）"等后缀。

本文件是内部模块，不被直接调用，只被同目录其他脚本 import。
"""
SCRIPT_INTERFACE = "internal-module"

import sys, os, csv, re, json, datetime, hashlib
from collections import Counter, defaultdict

def setup_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except Exception:
            pass

def skill_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def add_site_packages():
    """把隔离环境的 site-packages 挂进 sys.path（不硬编码用户名）。
    查找顺序：环境变量 BUDUI_SITE_PACKAGES → 解释器同级的 envs/* → 用户级 site。"""
    import glob
    cands = []
    env = os.environ.get('BUDUI_SITE_PACKAGES')
    if env:
        cands.append(env)
    p1 = os.path.dirname(os.path.abspath(sys.executable))
    p3 = os.path.dirname(os.path.dirname(p1))
    cands += glob.glob(os.path.join(p3, 'envs', '*', 'Lib', 'site-packages'))
    cands += glob.glob(os.path.join(p3, 'envs', '*', 'lib', 'python*', 'site-packages'))
    try:
        import site as _s
        usp = _s.getusersitepackages()
        cands += usp if isinstance(usp, list) else [usp]
    except Exception:
        pass
    added = []
    for c in cands:
        if c and os.path.isdir(c) and c not in sys.path:
            sys.path.insert(0, c)
            added.append(c)
    return added

def load_json(rel, default=None):
    p = os.path.join(skill_root(), rel)
    if not os.path.exists(p):
        return default if default is not None else {}
    with open(p, encoding='utf-8') as f:
        return json.load(f)

# 逻辑字段 → 候选列名片段（按优先级）
FIELD_RULES = [
    ('date',    ['数据日期', '日期'],            True),
    ('l1',      ['一级标签'],                    False),
    ('l2',      ['二级标签'],                    False),
    ('l3',      ['三级标签'],                    False),
    ('l4',      ['四级标签'],                    False),
    ('vp',      ['观点标签'],                    True),
    ('emotion', ['情感'],                        True),
    ('text',    ['内容', '声音片段', '摘要'],     True),
    ('summary', ['摘要'],                        False),
    ('snippet', ['声音片段'],                    False),
    ('model',   ['车型', '车系'],                True),
    ('vin',     ['VIN'],                         False),
    ('ccode',   ['车型码'],                      False),
    ('region',  ['大区'],                        False),
    ('channel', ['渠道'],                        False),
    # 只接受门店名称；专营店编码不能作为对外展示的门店维度。
    ('store',   ['专营店名称', '门店名称', '专营店'], False),
    ('uid',     ['模型声音ID', '声音ID'],        False),
    ('label_type', ['标签类型'],                 False),
]

def _strip_suffix(name):
    return re.sub(r'[（(].*?[)）]', '', str(name)).strip()

def detect_fields(columns):
    """返回 {逻辑字段: 实际列名}。必填字段缺失会抛错。"""
    stripped = {c: _strip_suffix(c) for c in columns}
    found, missing = {}, []
    for key, cands, required in FIELD_RULES:
        hit = None
        # 「专营店」的泛匹配会误命中「专营店编码」。没有名称列时宁可跳过，
        # 也不能把编码当作用户可读的门店名称。
        eligible = list(stripped.items())
        if key == 'store':
            eligible = [(c, s) for c, s in eligible
                        if not any(x in s.lower() for x in ('编码', 'code', 'id'))]
        # 精确匹配：按候选词的优先级顺序遍历，保证「车型」优先于「车系」
        for cd in cands:
            for c, s in eligible:
                if s == cd:
                    hit = c
                    break
            if hit:
                break
        # 再包含匹配
        if hit is None:
            for cd in cands:
                for c, s in eligible:
                    if cd in s and c != hit:
                        hit = c
                        break
                if hit:
                    break
        if hit:
            found[key] = hit
        elif required:
            missing.append(key)
    if missing:
        raise SystemExit(
            f'[字段识别失败] 缺少必需字段: {missing}\n'
            f'实际列名前 30 个: {list(columns)[:30]}'
        )
    if not any(found.get(key) for key in ('l2', 'l3', 'l4')):
        raise SystemExit(
            '[字段识别失败] 至少需要二级、三级、四级标签中的一个，才能建立对象口径。\n'
            f'实际列名前 30 个: {list(columns)[:30]}'
        )
    return found

def load_csv(path):
    if not os.path.exists(path):
        raise SystemExit(f'[数据文件不存在] {path}')
    with open(path, 'r', encoding='utf-8-sig', errors='replace', newline='') as f:
        rd = csv.DictReader(f)
        cols = rd.fieldnames or []
        rows = []
        for row_no, row in enumerate(rd, start=2):
            # CSV 行号与可选声音 ID 共同构成可复核的来源定位；不会写回用户源文件。
            row['__source_row__'] = row_no
            rows.append(row)
    fields = detect_fields(cols)
    return rows, fields, cols

def G(row, fields, key):
    """按逻辑字段取值，已 strip。"""
    col = fields.get(key)
    if not col:
        return ''
    return (row.get(col) or '').strip()

def source_ref(row, fields):
    """返回可回指源文件的稳定定位；ID 重复或缺失时仍可用 CSV 行号复核。"""
    uid = G(row, fields, 'uid')
    line = row.get('__source_row__', '')
    return f'声音ID={uid}｜CSV行={line}' if uid else f'CSV行={line}'

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def package_version():
    """manifest.json 是技能版本唯一来源；缺失时明确标为 unknown。"""
    data = load_json('manifest.json', {})
    return str(data.get('version') or 'unknown')

def text_blob(row, fields, use_tags=True):
    """检索用文本：正文（含摘要/声音片段）+ 标签 + 观点。
    口径匹配必须覆盖全部文本列，否则会漏掉只出现在摘要里的关键词。
    注意：主口径的关键字提取不应依赖此函数，见 tag_blob（）。"""
    keys = ['text', 'summary', 'snippet']
    if use_tags:
        keys += ['l1', 'l2', 'l3', 'l4', 'vp']
    parts = []
    for k in keys:
        v = G(row, fields, k)
        if v and v not in parts:
            parts.append(v)
    return ' | '.join(parts)

def tag_blob(row, fields):
    """检索用「结构化」文本：仅 1~4 级标签 + 规范观点（观点标签），
    不含正文 / 摘要 / 声音片段等自由文本字段。

    用途：主口径的关键字提取与容错扩展。保证「XX 相关」这类对象型主题
    永远只在固定的分类字段里取关键字，口径稳定、可复现，不受自由文本
    噪声（咨询、补偿、服务描述等）干扰。

    字段顺序：一级 → 二级 → 三级 → 四级 → 观点标签。
    """
    keys = ['l1', 'l2', 'l3', 'l4', 'vp']
    parts = []
    for k in keys:
        v = G(row, fields, k)
        if v and v not in parts:
            parts.append(v)
    return ' | '.join(parts)

def scope_tag_blob(row, fields):
    """主关键词口径使用二、三、四级标签与观点标签的合并字段。

    车型仍只走车型列；不纳入正文等自由文本，保证口径稳定、可复现。
    """
    return ' | '.join(v for k in ('l2', 'l3', 'l4', 'vp') if (v := G(row, fields, k)))

# ---------- 文本工具 ----------

# 情感归一词表：情感列取值不保证规范（可能有「正向」「好评」等变体）。
# 判序必须 负 → 正 → 中：「不满意」含「满意」，先判负面才能正确归类。
_EMO_NEG_WORDS = ('负面', '负向', '差评', '不满', '投诉', 'negative')
_EMO_POS_WORDS = ('正面', '正向', '好评', '满意', '点赞', '表扬', 'positive')
_EMO_NEU_WORDS = ('中性', '中立', 'neutral')

def emo_class(value):
    """情感值归一到 正面／中性／负面；无法归一返回 ''（不计入三档率）。"""
    v = (value or '').strip()
    if not v:
        return ''
    if any(w in v for w in _EMO_NEG_WORDS):
        return '负面'
    if any(w in v for w in _EMO_POS_WORDS):
        return '正面'
    if any(w in v for w in _EMO_NEU_WORDS):
        return '中性'
    return ''

def clip(text, n=132):
    """按标点收尾截断，禁止句中硬切。"""
    t = (text or '').strip()
    if len(t) <= n:
        return t
    seg = t[:n]
    for p in ('。', '；', '！', '？', '!', '?', ';'):
        i = seg.rfind(p)
        if i > n * 0.55:
            return seg[:i + 1]
    return seg + '…'

def quote_key(text):
    return re.sub(r'\s+', '', text or '')[:36]

def dedup_quotes(pairs, limit=None):
    """按原文指纹去重并保留附加元数据，如情感与来源行。"""
    seen, out = set(), []
    for item in pairs:
        if len(item) < 2:
            continue
        tag, text, *rest = item
        k = quote_key(text)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(tuple([tag, clip(text), *rest]))
        if limit and len(out) >= limit:
            break
    return out

def wan(v):
    """万分比格式化：中文表述，不用 ‱ 符号。"""
    return f'万分之 {v:.1f}'.replace('.0 ', ' ')

def pct(a, b, nd=1):
    return f'{a / b * 100:.{nd}f}%' if b else '—'

def safe_div(a, b):
    return a / b if b else 0.0

def parse_date(s):
    s = (s or '').strip()
    if not s:
        return None
    m = re.match(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', s)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None

def week_key(d):
    y, w, _ = d.isocalendar()
    return f'{y}-W{w:02d}'

def month_key(d):
    return f'{d.year}-{d.month:02d}'

# ---------- 周期定义 ----------

PERIOD_SPEC = {
    '日': {'name': '日报', 'grain': 'day', 'trend_window': 14, 'unit': '日'},
    '周': {'name': '周报', 'grain': 'week', 'trend_window': 8,  'unit': '周'},
    '月': {'name': '月报', 'grain': 'month', 'trend_window': 6, 'unit': '月'},
}

def period_key(d, grain):
    if grain == 'day':
        return d.isoformat()
    if grain == 'week':
        return week_key(d)
    return month_key(d)

def period_label(key, grain):
    if grain == 'day':
        return key[5:]                      # MM-DD
    if grain == 'week':
        year, week = key.split('-W')
        start = datetime.date.fromisocalendar(int(year), int(week), 1)
        end = start + datetime.timedelta(days=6)
        # 周序号对业务用户不可读，统一显示自然日期范围；跨年时带年份以消除歧义。
        if start.year != end.year:
            return f'{start:%Y/%m/%d}–{end:%Y/%m/%d}'
        return f'{start:%m/%d}–{end:%m/%d}'
    return key.split('-')[1] + '月'         # 07月
