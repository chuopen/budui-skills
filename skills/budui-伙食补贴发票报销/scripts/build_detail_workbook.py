#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
广九客运段节假日伙食补贴发票 → 交付明细 Excel + 问题报告

用法:
  python3 build_detail_workbook.py --invoice-dir <发票根目录> --dict-xlsx <工资号字典.xlsx> \
      [--out <输出.xlsx>] [--report <报告.md>] [--per-person 50] [--data-rows 20] \
      [--buyer-name 广深铁路股份有限公司广九客运段] [--buyer-tax 91440101721187389L] \
      [--department 广深动车队] \
      [--summary-out <每人汇总表.xlsx>] [--summary-title <标题>] [--summary-sheet <表名>] \
      [--summary-note <考勤说明>] [--summary-rows 35]

行为:
  1. 递归扫描 --invoice-dir 下所有 .pdf（含日期子文件夹），逐张提取
     发票号/开票日期/价税合计/购买方名称/购买方税号（pymupdf 文本层）。
  2. 按发票号查重：同号取文件名人名多的那张。
  3. 从文件名解析使用人（日期/公司名/号码/备用等噪音剔除后按分隔符切分），
     与工资号字典核对：字典外姓名照常输出并加单元格批注。
  4. 购买方名称+税号校验：不匹配的发票不进明细，列入问题报告。
  5. 实报金额 = min(人数×50, 发票金额)；备用票=0；
     文件名解析不出人名的非备用票 → 红字「待确认」、实报留空、加批注。
     发票金额-实报 ≥ 50 时在使用人后加红字「可加X人」。
  6. 按开票日期分 Sheet（2026.9.25 式命名），每表序号补足 20 行、SUM 合计行、
     考勤说明行、签名行；最后「合计」Sheet 按日期分组、序号每天重新计数。
  7. 每人汇总表（独立 xlsx）：当班天数 = 该人在有效票中出现的开票日期去重数，
     金额 = 天数×50；人员按金额从高到低排（同额保持字典序、字典外按首次出现）；
     内嵌「工资号」字典 sheet 供 VLOOKUP；宋体表单版式对齐 2026 春节交付样例。
  8. 输出 Markdown 问题报告（重复票、抬头异常、字典外姓名、待确认票、错位文件、
     汇总表对账）。

依赖: pymupdf, openpyxl
"""
import argparse, glob, json, os, re, sys, time

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Alignment, Border, Font, Side

# ---------------- PDF 提取 ----------------

def parse_pdf(path, tries=3):
    import fitz
    for i in range(tries):
        try:
            doc = fitz.open(path)
            page = doc[0]
            words = [(w[0], w[1], w[4]) for w in page.get_text("words")]
            doc.close()
            break
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(0.5)
    inv = {'invoiceNo': '', 'date': '', 'amount': None, 'buyer': '', 'buyerTax': ''}
    m20 = [w for x, y, w in words if re.fullmatch(r'\d{20}', w)]
    if m20:
        inv['invoiceNo'] = m20[0]
    md = [w for x, y, w in words if re.fullmatch(r'\d{4}年\d{1,2}月\d{1,2}日', w)]
    if md:
        inv['date'] = md[0]
    for x, y, w in words:
        if '小写' in w:
            row = [t for x2, y2, t in words
                   if abs(y2 - y) <= 6 and x2 > x and re.match(r'^[¥￥]?[\d,]+(\.\d+)?$', t)]
            if row:
                inv['amount'] = float(''.join(row).replace('¥', '').replace('￥', '').replace(',', ''))
            break
    buy = [w for x, y, w in words if 90 < y < 145 and x < 300
           and re.search(r'[\u4e00-\u9fa5]{2,}', w)
           and '名称' not in w and '统一' not in w and w not in ('购', '买', '方', '信', '息')]
    inv['buyer'] = buy[0] if buy else ''
    tax = [w for x, y, w in words if 90 < y < 145 and x < 300
           and re.fullmatch(r'[0-9A-Z]{17,20}', w)]
    inv['buyerTax'] = tax[0] if tax else ''
    return inv

# ---------------- 文件名人名解析 ----------------

def _segment_by_dict(s, dict_names):
    """无分隔符连写的人名串（如「李唐清刘军刘坚」）按工资号字典切分；
    每段 2–4 字且全部命中字典才接受，否则返回 None 交人工确认。"""
    def go(i, acc):
        if i == len(s):
            return list(acc)
        for ln in (4, 3, 2):
            if s[i:i + ln] and s[i:i + ln] in dict_names:
                acc.append(s[i:i + ln])
                r = go(i + ln, acc)
                if r:
                    return r
                acc.pop()
        return None
    return go(0, [])


def parse_names(filename, dict_names):
    t = os.path.basename(filename).replace('.pdf', '')
    is_backup = '备用' in t
    t = re.sub(r'\d{4}年\s*\d{1,2}\s*月\s*\d{1,2}\s*[日号]?', '', t)
    t = re.sub(r'\d{1,2}\s*月\s*\d{1,2}\s*[日号]?', '', t)   # 「10 月 7」缺「日」也能剔除
    t = re.sub(r'\d{1,2}\s*[.，,]\s*\d{1,2}\s*[日号]?', '', t)  # 「10.7号」「10，2日」
    t = re.sub(r'广深铁路股份有限公司广九客运段', '', t)
    t = re.sub(r'\d{20}', '', t)
    for w in ['备用', '加餐', '伙食补贴', '餐补', '发票', '多50元', '100元', '50元', '50', '元']:
        t = t.replace(w, '')
    t = re.sub(r'\(\d\)', '', t).replace('_', '')
    t = re.sub(r'^[，,、\s.。（）/]+|[，,、\s.。（）]+$', '', t)
    parts = [p for p in re.split(r'[、，,\s.。和（）/]+', t) if p]
    names, leftover = [], []
    for p in parts:
        p = re.sub(r'^[^\u4e00-\u9fa5]+|[^\u4e00-\u9fa5]+$', '', p)  # 「925贺天镛」「耿楠楠d」
        if not p:
            continue
        p = re.sub(r'^[\u4e00-\u9fa5]{0,4}\d{1,4}班(?=[\u4e00-\u9fa5])', '', p)  # 「动78班范光付」
        if re.fullmatch(r'[\u4e00-\u9fa5]{2,4}', p):
            names.append(p)
        elif re.fullmatch(r'[\u4e00-\u9fa5]{5,}', p) and dict_names:
            seg = _segment_by_dict(p, dict_names)
            if seg:
                names.extend(seg)
            else:
                leftover.append(p)
        elif len(p) > 4:
            leftover.append(p)
    not_in_dict = [n for n in names if n not in dict_names]
    return names, not_in_dict, is_backup, leftover

# ---------------- 样式 ----------------

THIN = Side(style='thin')
BORDER = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
LEFT = Alignment(horizontal='left', vertical='center', wrap_text=True)
F_TITLE = Font(name='苹方-简', size=18, bold=True)
F_DEPT = Font(name='苹方-简', size=11)
F_HEAD = Font(name='苹方-简', size=12)
F_DATA = Font(name='苹方-简', size=11)
F_FCOL = Font(name='苹方-简', size=10)
F_GCOL = Font(name='苹方-简', size=8)
F_RED = Font(name='苹方-简', size=8, color='FFFF0000')
F_NOTE = Font(name='苹方-简', size=12)
CN_NUM = {1: '一', 2: '两', 3: '三', 4: '四', 5: '五', 6: '六', 7: '七', 8: '八', 9: '九'}


def load_dict(dict_xlsx, sheet='工资号'):
    import openpyxl
    wb = openpyxl.load_workbook(dict_xlsx, read_only=True)
    ws = wb[sheet] if sheet in wb.sheetnames else wb[wb.sheetnames[0]]
    names = {}
    for row in ws.iter_rows(min_row=1, values_only=True):
        if row and row[0] and isinstance(row[0], str) and len(row) > 1:
            names[row[0].strip()] = (row[1], row[2] if len(row) > 2 else '')
    wb.close()
    return names


def collect_pdfs(invoice_dir):
    pdfs = []
    for root, dirs, files in os.walk(invoice_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.lower().endswith('.pdf') and not f.startswith('._'):
                pdfs.append(os.path.join(root, f))
    return sorted(pdfs)


# ---------------- 每人汇总表 ----------------

S_CENTER = Alignment(horizontal='center', vertical='center')
S_LEFT = Alignment(horizontal='left', vertical='center')


def build_summary_workbook(path, title, sheet_name, note, people, dict_names,
                           department, per_person, data_rows):
    """people: [(姓名, 是否在字典, 职名或None, 当班天数)]，顺序即输出顺序。
    版式对齐 2026 春节交付样例：宋体无加粗、A–G 细边框、序号 numfmt '0_ '、
    工资号列 VLOOKUP 内嵌「工资号」字典 sheet、金额 =天数×50、总计行、
    考勤说明行、签名行、竖向打印 A1:G。"""
    wb = Workbook()
    wb.remove(wb.active)
    wb.calculation.fullCalcOnLoad = True
    ws = wb.create_sheet(sheet_name)
    f_title = Font(name='宋体', size=20)
    f12 = Font(name='宋体', size=12)
    f11 = Font(name='宋体', size=11)
    ft = Font(name='Times New Roman', size=12)

    ws.merge_cells('A1:G1'); ws.row_dimensions[1].height = 32.25
    c = ws['A1']; c.value = title; c.font = f_title; c.alignment = S_CENTER
    ws.row_dimensions[2].height = 23.25
    c = ws['A2']; c.value = '部门（公章）：XX'; c.font = f12; c.alignment = S_LEFT
    for i, h in enumerate(['序号', '部  门', '工资号', '姓 名', '职 名', '当班天数', '金额'], 1):
        c = ws.cell(row=3, column=i, value=h)
        c.font = f12; c.alignment = S_CENTER; c.border = BORDER
    ws.row_dimensions[3].height = 24.95
    for col, w in zip('ABCDEFG', (5.375, 14.01, 15.625, 14.01, None, None, 14.01)):
        if w:
            ws.column_dimensions[col].width = w

    r = 4
    for i, (name, in_dict, job, days) in enumerate(people, 1):
        vals = [i, department, f'=VLOOKUP(D{r},工资号!A:B,2,0)' if in_dict else None,
                name, job, days, f'=F{r}*{per_person}']
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=r, column=ci, value=v)
            c.border = BORDER
            c.font = ft if ci == 3 else (f11 if ci == 4 else f12)
            c.alignment = S_CENTER
            if ci == 1:
                c.number_format = '0_ '
        ws.row_dimensions[r].height = 18.95
        r += 1
    for i in range(len(people) + 1, data_rows + 1):  # 空行补足（SUM 一并盖住，便于手工补人）
        for ci in range(1, 8):
            c = ws.cell(row=r, column=ci)
            c.border = BORDER; c.font = f12; c.alignment = S_CENTER
            if ci == 1:
                c.number_format = '0_ '
        ws.cell(row=r, column=1, value=i)
        ws.row_dimensions[r].height = 18.95
        r += 1
    ws.cell(row=r, column=2, value='总 计')
    ws.cell(row=r, column=6, value=f'=SUM(F4:F{r - 1})')
    ws.cell(row=r, column=7, value=f'=SUM(G4:G{r - 1})')
    for ci in range(2, 8):
        c = ws.cell(row=r, column=ci)
        c.border = BORDER; c.font = f12; c.alignment = S_CENTER
    r += 1
    ws.merge_cells(f'A{r}:G{r}')  # 不合并会被居中裁掉左半句（文字宽于 A 列）
    c = ws.cell(row=r, column=1, value=f'{note}，以上员工的当班天数、日期与考勤相符')
    c.font = f12; c.alignment = S_CENTER
    r += 1
    c = ws.cell(row=r, column=1,
                value='制表人：              部门负责人：                分管领导：')
    c.font = f12; c.alignment = S_LEFT

    wd = wb.create_sheet('工资号')
    for i, (n, (gid, job)) in enumerate(dict_names.items(), 1):
        wd.cell(row=i, column=1, value=n).font = f11
        wd.cell(row=i, column=2, value=gid).font = f11
        if job:
            wd.cell(row=i, column=3, value=job).font = f11
    wd.sheet_state = 'hidden'  # 仅作 VLOOKUP 数据源，样例如此（不进打印）

    ws.print_area = f'A1:G{r}'
    ws.page_setup.orientation = 'portrait'
    ws.page_setup.paperSize = 9  # A4；样例靠窄边距把 41 行压进一页，勿用默认 Letter
    ws.page_margins.left = ws.page_margins.right = 0.24
    ws.page_margins.top = ws.page_margins.bottom = 0.2
    wb.save(path)


def main():
    ap = argparse.ArgumentParser(description='伙食补贴发票 → 报销明细 Excel')
    ap.add_argument('--invoice-dir', required=True)
    ap.add_argument('--dict-xlsx', required=True, help='含「工资号」sheet 的字典 xlsx')
    ap.add_argument('--out', default=None, help='输出 xlsx 路径（默认写在 invoice-dir 下）')
    ap.add_argument('--report', default=None, help='输出 Markdown 报告路径')
    ap.add_argument('--per-person', type=int, default=50)
    ap.add_argument('--data-rows', type=int, default=20, help='每表序号补足到的行数')
    ap.add_argument('--buyer-name', default='广深铁路股份有限公司广九客运段')
    ap.add_argument('--buyer-tax', default='91440101721187389L')
    ap.add_argument('--department', default='广深动车队')
    ap.add_argument('--atten-note', action='append', default=[],
                    help='考勤说明行假期范围，格式 日期=说明前缀，如 2026.9.25=9月25-27日（可多次）')
    ap.add_argument('--title', default='节日专项伙食补贴报销电子发票使用明细表（七大组）')
    ap.add_argument('--workbook-name', default='七大组节假日专项伙食补贴报销电子发票使用明细表.xlsx')
    ap.add_argument('--summary-out', default=None, help='每人汇总表 xlsx 路径（默认与明细同目录、按标题命名）')
    ap.add_argument('--summary-title', default='节日专项伙食补贴汇总表（七大组）')
    ap.add_argument('--summary-sheet', default='餐补汇总表', help='汇总表 Sheet 名（如 餐补汇总表（无餐车））')
    ap.add_argument('--summary-note', default=None,
                    help='汇总表考勤说明（如 2月17-22日）；默认按有效票日期范围自动生成')
    ap.add_argument('--summary-rows', type=int, default=35, help='汇总表数据区总行数（含补足空行）')
    args = ap.parse_args()

    dict_names = load_dict(args.dict_xlsx)
    files = collect_pdfs(args.invoice_dir)
    if not files:
        sys.exit(f'未在 {args.invoice_dir} 下找到 PDF')

    # ---- 提取 + 整理 ----
    records, seen_no, mismatches, dups, unparsed = [], {}, [], [], []
    for f in files:
        r = parse_pdf(f)
        r['file'] = os.path.relpath(f, args.invoice_dir)
        r['folder'] = os.path.basename(os.path.dirname(f))
        inv_no = r['invoiceNo']
        m = re.search(r'(\d{4})年(\d{2})月(\d{2})日', r['date'])
        if not m:
            reason = ('无文本层（扫描/拍照件），提取不到任何字段' if not r['date'] and not inv_no
                      else f'开票日期无法识别「{r["date"] or "空"}」')
            unparsed.append((r['file'], reason, inv_no, r['amount']))
            continue
        rec_date = f'{int(m.group(1))}.{int(m.group(2))}.{int(m.group(3))}'
        date_cn = f'{int(m.group(2))}月{int(m.group(3))}日'
        names, not_in_dict, is_backup, leftover = parse_names(r['file'], dict_names)
        pending = False
        prev = seen_no.get(inv_no) if inv_no else None  # 查重：取人名多的
        if prev is not None:
            if len(names) > len(prev['names']):
                records.remove(prev)
                dups.append((inv_no, r['file'], prev['file']))
                seen_no.pop(inv_no)  # 新记录在下方替换入库
            else:
                dups.append((inv_no, prev['file'], r['file']))
                continue
        if not names and not is_backup:
            pending = True  # 文件名无使用人且非备用 → 待确认
        buyer_bad = not (r['buyer'] == args.buyer_name and r['buyerTax'] == args.buyer_tax)
        rec = dict(date=rec_date, date_cn=date_cn, invoice_no=inv_no, amount=r['amount'],
                   names=names, not_in_dict=not_in_dict, leftover=leftover,
                   is_backup=is_backup, pending=pending,
                   buyer_bad=buyer_bad, buyer=r['buyer'], buyer_tax=r['buyerTax'],
                   file=r['file'], folder=r['folder'])
        records.append(rec)
        if inv_no:
            seen_no[inv_no] = rec  # 提取不出号码的票不做查重,全部保留
        fm = re.search(r'\d{20}', r['file'])
        if fm and inv_no and fm.group(0) != inv_no:
            mismatches.append((r['file'], fm.group(0), inv_no))

    def reimb(rec):
        if rec['is_backup']:
            return 0
        if rec['pending'] or rec['buyer_bad'] or rec['amount'] is None:
            return None
        return min(len(rec['names']) * args.per_person, int(rec['amount'] // 1))

    def can_add(rec):
        if rec['is_backup'] or rec['pending'] or rec['buyer_bad'] or rec['amount'] is None:
            return 0
        e = reimb(rec)
        return int((rec['amount'] - e) // args.per_person) if e is not None else 0

    detail = {}
    for rec in records:
        if rec['buyer_bad']:
            continue
        detail.setdefault(rec['date'], []).append(rec)
    for d in detail:
        detail[d].sort(key=lambda r: r['is_backup'])  # 备用排末尾
    bad_invoices = [r for r in records if r['buyer_bad']]
    pending_invoices = [r for r in records if r['pending'] and not r['buyer_bad']]

    # 同人同天多张有效票：每人每天只能报一次
    per_day = {}
    for rec in records:
        if rec['is_backup'] or rec['pending'] or rec['buyer_bad']:
            continue
        for n in rec['names']:
            per_day.setdefault((rec['date'], n), []).append(rec['file'])
    person_conflicts = {k: v for k, v in per_day.items() if len(v) > 1}

    # ---- 建工作簿 ----
    atten_map = {}
    for kv in args.atten_note:
        k, _, v = kv.partition('=')
        atten_map[k.strip()] = v.strip() or k.strip()

    wb = Workbook()
    wb.remove(wb.active)
    wb.calculation.fullCalcOnLoad = True

    def sheet_layout(ws, title_note):
        ws.merge_cells('A1:H1'); ws.row_dimensions[1].height = 39
        c = ws['A1']; c.value = args.title; c.font = F_TITLE; c.alignment = CENTER
        ws.merge_cells('A2:C2'); ws.row_dimensions[2].height = 18
        c = ws['A2']; c.value = '部门（章）：XX'; c.font = F_DEPT; c.alignment = LEFT
        for i, h in enumerate(['序号', '发票号码', '开票日期', '发票金额', '实际报销金额',
                               '使用部门', '使用人', title_note], 1):
            c = ws.cell(row=3, column=i, value=h)
            c.font = F_HEAD; c.alignment = CENTER; c.border = BORDER
        ws.row_dimensions[3].height = 21.75
        for col, w in zip('ABCDEFGHI', (4.9, 24.2, 11.2, 9.1, 13.8, 11.9, 38.0, 25.9, 6.0)):
            ws.column_dimensions[col].width = w

    def fill_rows(ws, recs):
        r = 4
        for i, rec in enumerate(recs, 1):
            e = reimb(rec)
            add = can_add(rec)
            if rec['is_backup']:
                users, users_font = '备用', F_RED
            elif rec['pending']:
                users, users_font = '待确认', F_RED
            else:
                users = '、'.join(rec['names']) + (f'、可加{CN_NUM[add]}人' if add > 0 else '')
                users_font = None
            vals = [i, rec['invoice_no'], rec['date'], rec['amount'],
                    e if e is not None else None, args.department, users,
                    None if rec['is_backup'] else f"{rec['date_cn']}伙食补贴"]
            for ci, v in enumerate(vals, 1):
                c = ws.cell(row=r, column=ci, value=v)
                c.border = BORDER
                if ci == 2:
                    c.number_format = '@'
                c.font = F_FCOL if ci == 6 else (users_font or F_GCOL if ci == 7 else F_DATA)
                c.alignment = LEFT if ci == 7 else CENTER
            if add > 0 and not rec['is_backup'] and not rec['pending']:
                base = '、'.join(rec['names']) + '、'
                ws.cell(row=r, column=7).value = CellRichText(
                    TextBlock(InlineFont(rFont='苹方-简', sz=8), base),
                    TextBlock(InlineFont(rFont='苹方-简', sz=8, color='FF0000'),
                              f'可加{CN_NUM[add]}人'))
            # 批注：字典外姓名 / 待确认
            notes = [f'「{n}」不在工资号字典中，可能为新员工，请核实。' for n in rec['not_in_dict']]
            if rec['pending']:
                notes.append(f'该发票（{rec["invoice_no"]}，{rec["amount"]}元）文件名未注明使用人，'
                             f'请确认后补填使用人与实报金额。')
            if notes:
                cm = Comment('\n'.join(notes), 'budui')
                cm.width, cm.height = 280, 120
                ws.cell(row=r, column=7).comment = cm
            if e is not None:
                c = ws.cell(row=r, column=9, value=f'=INT((D{r}-E{r})/{args.per_person})')
                c.font = F_DATA; c.alignment = CENTER
            ws.row_dimensions[r].height = 21
            r += 1
        for i in range(len(recs) + 1, args.data_rows + 1):  # 空行补足
            for ci in range(1, 9):
                c = ws.cell(row=r, column=ci)
                c.border = BORDER; c.font = F_DATA; c.alignment = CENTER
                if ci == 2:
                    c.number_format = '@'
            ws.cell(row=r, column=1, value=i)
            ws.row_dimensions[r].height = 21
            r += 1
        last = max(3 + args.data_rows, 3 + len(recs))  # 票数超过 20 时 SUM 必须盖住全部数据行
        ws.cell(row=r, column=2, value='合计')
        ws.cell(row=r, column=4, value=f'=SUM(D4:D{last})')
        ws.cell(row=r, column=5, value=f'=SUM(E4:E{last})')
        for ci in range(1, 9):
            c = ws.cell(row=r, column=ci)
            c.border = BORDER; c.font = F_DATA; c.alignment = CENTER
        ws.row_dimensions[r].height = 21
        r += 1
        ws.merge_cells(f'A{r}:H{r}'); ws.row_dimensions[r].height = 17.6
        day = recs[0]['date_cn'] if recs else ''
        c = ws.cell(row=r, column=1, value=f'{day}，以上员工的当班天数、日期与考勤相符')
        c.font = F_NOTE; c.alignment = CENTER
        r += 1
        ws.merge_cells(f'A{r}:B{r}')
        c = ws.cell(row=r, column=1, value='制表人：'); c.font = F_DEPT; c.alignment = LEFT
        ws.merge_cells(f'D{r}:E{r}')
        c = ws.cell(row=r, column=4, value='部门负责人：'); c.font = F_DEPT; c.alignment = LEFT
        c = ws.cell(row=r, column=7, value='分管领导：'); c.font = F_DEPT; c.alignment = LEFT
        return r

    def date_key(k):
        return tuple(int(x) for x in k.split('.'))

    for date in sorted(detail, key=date_key):
        ws = wb.create_sheet(date)
        sheet_layout(ws, f'所属节日（{date}）')
        end = fill_rows(ws, detail[date])
        atten = atten_map.get(date, detail[date][0]['date_cn'])
        ws.cell(row=end - 1, column=1).value = \
            f'{atten}，以上员工的当班天数、日期与考勤相符'

    ws = wb.create_sheet('合计')
    ws.row_dimensions[1].height = 17.6
    for i, h in enumerate(['序号', '发票号码', '开票日期', '发票金额', '实际报销金额',
                           '使用部门', '使用人', '所属节日'], 1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = F_HEAD; c.alignment = CENTER; c.border = BORDER
    for col, w in zip('ABCDEFGHI', (6.3, 24.8, 18.9, 9.1, 13.8, 11.9, 29.5, 25.9, 9.6)):
        if w:
            ws.column_dimensions[col].width = w
    r = 2
    for date in sorted(detail, key=date_key):
        for i, rec in enumerate(detail[date], 1):
            e = reimb(rec)
            add = can_add(rec)
            if rec['is_backup']:
                users = '备用'
            elif rec['pending']:
                users = '待确认'
            else:
                users = '、'.join(rec['names']) + (f'、可加{CN_NUM[add]}人' if add > 0 else '')
            vals = [i, rec['invoice_no'], rec['date'], rec['amount'],
                    e if e is not None else None, args.department, users,
                    None if rec['is_backup'] else f'{rec["date_cn"]}伙食补贴']
            for ci, v in enumerate(vals, 1):
                c = ws.cell(row=r, column=ci, value=v)
                c.border = BORDER
                if ci == 2:
                    c.number_format = '@'
                c.font = F_FCOL if ci == 6 else (F_RED if (rec['is_backup'] or rec['pending']) and ci == 7 else F_GCOL if ci == 7 else F_DATA)
                c.alignment = LEFT if ci == 7 else CENTER
            if add > 0 and not rec['is_backup'] and not rec['pending']:
                base = '、'.join(rec['names']) + '、'
                ws.cell(row=r, column=7).value = CellRichText(
                    TextBlock(InlineFont(rFont='苹方-简', sz=8), base),
                    TextBlock(InlineFont(rFont='苹方-简', sz=8, color='FF0000'),
                              f'可加{CN_NUM[add]}人'))
            if e is not None:
                c = ws.cell(row=r, column=9, value=f'=INT((D{r}-E{r})/{args.per_person})')
                c.font = F_DATA; c.alignment = CENTER
            ws.row_dimensions[r].height = 21
            r += 1

    # 打印设置：明细区 A:H，按宽度缩放
    for sn in wb.sheetnames:
        ws = wb[sn]
        ws.print_area = f'A1:H{ws.max_row}'
        ws.page_setup.scale = None
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_margins.left = ws.page_margins.right = 0.71
        ws.page_margins.top = ws.page_margins.bottom = 0.75

    out = args.out or os.path.join(args.invoice_dir, args.workbook_name)
    wb.save(out)
    print(f'已生成: {out}')

    # ---- 汇总输出 ----
    total_d = total_e = 0
    for date in sorted(detail, key=date_key):
        recs = detail[date]
        d_sum = sum(x['amount'] or 0 for x in recs)
        e_sum = sum(x for x in (reimb(x) for x in recs) if x)
        total_d += d_sum; total_e += e_sum
        print(f'  {date}: {len(recs)}张 发票金额={d_sum:g} 实报={e_sum:g}')
    print(f'  合计: 发票金额={total_d:g} 实报={total_e:g}')
    print(f'  抬头异常(未计入): {len(bad_invoices)}张; 待确认: {len(pending_invoices)}张; '
          f'同号重复剔除: {len(dups)}; 同人同天冲突: {len(person_conflicts)}; '
          f'文件名内嵌发票号不一致: {len(mismatches)}; 无法解析: {len(unparsed)}')

    # ---- 每人汇总表：当班天数 = 有效票开票日期去重数 ----
    person_days, extra_order = {}, []
    for rec in records:
        if rec['is_backup'] or rec['pending'] or rec['buyer_bad'] or rec['amount'] is None:
            continue
        for n in rec['names']:
            if n not in person_days:
                person_days[n] = set()
                if n not in dict_names:
                    extra_order.append(n)
            person_days[n].add(rec['date'])
    people = []
    for n in list(dict_names) + extra_order:  # 同金额时按此顺序稳定顺延：字典序在前、字典外按首次出现
        if n in person_days:
            people.append((n, n in dict_names, dict_names.get(n, (None, None))[1] or None,
                           len(person_days[n])))
    people.sort(key=lambda p: -p[3])  # 汇总表按金额（天数×50）从高到低；工资号为空不特殊处理，金额高照样排前
    if person_days:
        ds = sorted(tuple(int(x) for x in d.split('.')) for v in person_days.values() for d in v)
        (y1, m1, d1), (y2, m2, d2) = ds[0], ds[-1]
        auto_note = (f'{m1}月{d1}-{d2}日' if (y1, m1) == (y2, m2)
                     else f'{m1}月{d1}日-{m2}月{d2}日')
    else:
        auto_note = ''
    note = args.summary_note or auto_note
    person_day_total = sum(len(v) for v in person_days.values())
    summary_total = person_day_total * args.per_person
    row_subsidy = cap_loss = add_bonus = 0
    for rec in records:
        if rec['is_backup'] or rec['pending'] or rec['buyer_bad'] or rec['amount'] is None:
            continue
        e = reimb(rec)
        n = len(rec['names'])
        row_subsidy += n * args.per_person
        cap_loss += max(0, n * args.per_person - e)
        add_bonus += can_add(rec) * args.per_person
    dup_extra = sum(len(v) - 1 for v in person_conflicts.values())
    summary_out = args.summary_out or os.path.join(
        os.path.dirname(os.path.abspath(out)), args.summary_title + '.xlsx')
    build_summary_workbook(summary_out, args.summary_title, args.summary_sheet, note,
                           people, dict_names, args.department, args.per_person,
                           args.summary_rows)
    print(f'已生成: {summary_out}（{len(people)}人 {person_day_total}人天 总计{summary_total}元）')

    # ---- 问题报告 ----
    report = args.report or os.path.splitext(out)[0] + '-问题报告.md'
    L = [f'# 伙食补贴报销交付问题报告', '',
         f'- 发票目录：`{args.invoice_dir}`',
         f'- 交付文件：`{os.path.basename(out)}`',
         f'- 扫描 PDF：{len(files)} 张（无法解析 {len(unparsed)} 张，见下文）；'
         f'按发票号查重后 {len(records)} 张'
         f'（有效 {sum(len(v) for v in detail.values())} 张，抬头异常 {len(bad_invoices)} 张未计入）', '']
    if pending_invoices:
        L += ['## 待确认（文件名无使用人，表内已标红）', '']
        for rec in pending_invoices:
            L.append(f'- {rec["file"]}：发票号 {rec["invoice_no"]}，{rec["amount"]}元，'
                     f'{rec["date_cn"]}——请告知使用人后补填实报')
        L.append('')
    if bad_invoices:
        L += ['## 抬头异常（未计入，需退回重开）', '',
              f'正确抬头：{args.buyer_name} / 税号 {args.buyer_tax}', '']
        for rec in bad_invoices:
            L.append(f'- {rec["file"]}：发票号 {rec["invoice_no"]}，{rec["amount"]}元，'
                     f'购买方为「{rec["buyer"]}」税号「{rec["buyer_tax"] or "无"}」')
        L.append('')
    if unparsed:
        L += ['## 无法解析的 PDF（未计入，需人工处理）', '',
              '以下 PDF 提取不到开票日期，整张未进明细；请对照原件人工核对后处理：', '']
        for f, reason, no, amt in unparsed:
            L.append(f'- {f}：{reason}'
                     + (f'（文件名内嵌发票号 {no}）' if no else '')
                     + (f'，金额约 {amt} 元' if amt is not None else ''))
        L.append('')
    L += ['## 查重结果（按发票号）', '']
    if dups:
        L += ['同一发票号出现多个 PDF，保留文件名人名多的那张（同数保留先出现的）：', '']
        for no, kept, dropped in dups:
            L.append(f'- 发票号 {no}：保留 `{kept}`，剔除 `{dropped}`')
        L.append('')
    else:
        L += ['所有发票号均唯一，无重复。', '']
    if person_conflicts:
        L += ['## 同人同天多张有效票（每人每天只能报一次，请核实）', '']
        for (date, n), fs in sorted(person_conflicts.items()):
            L.append(f'- {date} {n}：{"、".join("`" + f + "`" for f in fs)}')
        L.append('')
    dict_missing = sorted({n for rec in records for n in rec['not_in_dict']})
    if dict_missing:
        L += ['## 不在工资号字典的姓名（已照常输出并加批注，请核实是否新员工）', '']
        for n in dict_missing:
            files_n = [rec['file'] for rec in records if n in rec['not_in_dict']]
            L.append(f'- {n}：{len(files_n)} 张票（{"、".join(files_n)}）')
        L.append('')
    glued_left = [(rec['file'], frag) for rec in records for frag in rec['leftover']]
    if glued_left:
        L += ['## 文件名疑似连写人名、无法按字典拆分（请人工核对使用人是否遗漏）', '']
        for f, frag in glued_left:
            L.append(f'- {f}：片段「{frag}」')
        L.append('')
    if mismatches:
        L += ['## 文件名内嵌发票号与 PDF 不一致', '']
        for f, a, b in mismatches:
            L.append(f'- {f}: 文件名 {a} vs PDF {b}')
        L.append('')
    folder_warn = []
    for rec in records:
        fm_ = re.search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日', rec['folder'])
        if fm_ and rec['date_cn'] != f'{int(fm_.group(1))}月{int(fm_.group(2))}日':
            folder_warn.append(f'- {rec["file"]}：放在「{rec["folder"]}」但开票日期是 {rec["date_cn"]}，已按开票日期归组')
    if folder_warn:
        L += ['## 文件夹与开票日期不符（已按开票日期归组）', ''] + folder_warn + ['']
    L += ['## 汇总表对账（每人汇总表 ← 明细有效票）', '',
          f'- 汇总表 `{os.path.basename(summary_out)}`：{len(people)} 人、'
          f'{person_day_total} 人天、总计 {summary_total:g} 元',
          f'- 明细实报合计：{total_e:g} 元']
    diff = total_e - summary_total
    if diff == 0 and add_bonus == 0 and cap_loss == 0 and dup_extra == 0:
        L += ['- 汇总总计与明细实报一致。', '']
    else:
        L += [f'- 差额 {diff:g} 元 = 可加X人补贴 +{add_bonus:g} 元 − 发票封顶少算 {cap_loss:g} 元 '
              f'+ 同人同天重复计 {dup_extra * args.per_person:g} 元（重复明细见上文冲突节）。'
              '备用/待确认/抬头异常票不计入汇总表；待确认票确认后重跑脚本再交付。', '']
    L += ['## 汇总', '', '| Sheet | 张数 | 发票金额 | 实报金额 |', '|---|---|---|---|']
    for date in sorted(detail):
        recs = detail[date]
        L.append(f'| {date} | {len(recs)} | {sum(x["amount"] or 0 for x in recs):g} | '
                 f'{sum(x for x in (reimb(x) for x in recs) if x):g} |')
    L += [f'| **合计** | **{sum(len(v) for v in detail.values())}** | **{total_d:g}** | **{total_e:g}** |', '']
    if not args.atten_note:
        L.append('> 提示：考勤说明行默认写当天日期，如假期为连续多天可用 --atten-note 日期=说明 指定，如 --atten-note 2026.9.25=9月25-27日。')
    with open(report, 'w', encoding='utf-8') as fp:
        fp.write('\n'.join(L))
    print(f'已生成: {report}')


if __name__ == '__main__':
    main()
