#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归用例:覆盖 2026-10 中秋+国庆交付中发现并修复的缺陷。

覆盖点:
  1. 同发票号查重取人名多的那张,且被剔除票的替代记录要入库
     (旧 bug:后文件人名更多时删旧不增新,该发票整个消失)
  2. 文件名日期为全角逗号「10，2日」时仍按日期剔除,人名不粘连
  3. PDF 提取不出 20 位发票号的票不做查重,多张共存
  4. 同人同天多张有效票在报告中列出冲突
  5. 班组前缀「动78班」粘住人名时仍解析出人名(此前漏人导致少报)
  6. 缺「日」的日期「10 月 7」+ 尾部噪音「d」+ 连写人名按字典拆分
  7. 前导数字「925」与日期后缀「号」不粘人名
  8. 无文本层 PDF 不再静默丢弃,报告列出「无法解析」节
  9. 单日票数超过 20,合计行 SUM 覆盖全部数据行
 10. 每人汇总表:字典序输出、当班天数按日期去重(同人同天冲突只算 1 天)、
     字典外人员垫底且工资号/职名留空、金额=天数×50、总计行、内嵌工资号 sheet、
     报告有「汇总表对账」节(差额=同人同天重复计)

运行: python3 evals/test_regressions_202610.py
全部通过打印 PASS 退出 0;任一失败打印 FAIL 退出 1。
依赖: pymupdf、openpyxl
"""
import os, subprocess, sys, tempfile

import fitz, openpyxl

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(SKILL, 'scripts', 'build_detail_workbook.py')


def make_pdf(path, inv_no, date_cn, amount,
             buyer='广深铁路股份有限公司广九客运段', tax='91440101721187389L'):
    doc = fitz.open()
    page = doc.new_page(width=595, height=420)
    page.insert_text((40, 40), '电子发票（普通发票）', fontsize=9, fontname='china-s')
    page.insert_text((70, 100), buyer, fontsize=9, fontname='china-s')
    page.insert_text((70, 130), tax, fontsize=9, fontname='courier')
    if inv_no:
        page.insert_text((40, 200), inv_no, fontsize=9, fontname='courier')
    page.insert_text((40, 220), date_cn, fontsize=9, fontname='china-s')
    page.insert_text((300, 300), '小写', fontsize=9, fontname='china-s')
    page.insert_text((340, 300), f'¥{amount}', fontsize=9, fontname='courier')
    doc.save(path)
    doc.close()


def main():
    tmp = tempfile.mkdtemp(prefix='budui_regress_')
    inv = os.path.join(tmp, 'invoices')
    os.makedirs(f'{inv}/10 月 1 日')
    os.makedirs(f'{inv}/10 月 2 日')

    dict_wb = openpyxl.Workbook()
    ws = dict_wb.active
    ws.title = '工资号'
    for i, n in enumerate(['张三', '李四', '王五', '赵六', '钱七', '欧阳锋', '耿楠楠'], 1):
        ws.cell(row=i, column=1, value=n)
        ws.cell(row=i, column=2, value=f'ZG0000{i}')
    dict_x = os.path.join(tmp, 'dict.xlsx')
    dict_wb.save(dict_x)

    # 用例1:同号两张,后文件人名多 → 保留后者并入库
    make_pdf(f'{inv}/10 月 2 日/a_26442000011334972541.pdf', '26442000011334972541', '2026年10月02日', '98')
    make_pdf(f'{inv}/10 月 2 日/b 张三26442000011334972541.pdf', '26442000011334972541', '2026年10月02日', '98')
    # 用例2:全角逗号日期,两人名
    make_pdf(f'{inv}/10 月 2 日/10，2日李四 王五26442000011322630931.pdf', '26442000011322630931', '2026年10月02日', '107')
    # 用例3:同人同天两张有效票
    make_pdf(f'{inv}/10 月 2 日/10.2张三26442000011334971001.pdf', '26442000011334971001', '2026年10月02日', '55')
    make_pdf(f'{inv}/10 月 2 日/10月2日张三26442000011334971002.pdf', '26442000011334971002', '2026年10月02日', '55')
    # 用例4:PDF 无 20 位号的两张票,不互相误判为重复
    make_pdf(f'{inv}/10 月 1 日/10.1赵六.pdf', None, '2026年10月01日', '52')
    make_pdf(f'{inv}/10 月 1 日/10.1钱七.pdf', None, '2026年10月01日', '52')
    # 用例5:班组前缀粘人名(此前「动78班李四」解析不出人,谢宇轩被静默漏掉少报)
    make_pdf(f'{inv}/10 月 2 日/10月2日，动78班李四26442000011334972001.pdf',
             '26442000011334972001', '2026年10月02日', '66')
    # 用例6:缺「日」日期+尾部拉丁噪音+连写人名按字典拆分(≥5字才拆,4字与合法复姓不分)
    make_pdf(f'{inv}/10 月 2 日/10 月 2张三李四王五d26442000011334972002.pdf',
             '26442000011334972002', '2026年10月02日', '150')
    make_pdf(f'{inv}/10 月 2 日/10 月 2欧阳锋耿楠楠d26442000011334972003.pdf',
             '26442000011334972003', '2026年10月02日', '100')
    # 用例7:前导数字、日期后缀「号」
    make_pdf(f'{inv}/10 月 2 日/925赵六）26442000011334972004.pdf',
             '26442000011334972004', '2026年10月02日', '55')
    make_pdf(f'{inv}/10 月 2 日/10.2号钱七26442000011334972005.pdf',
             '26442000011334972005', '2026年10月02日', '55')
    # 用例8:无文本层 PDF,报告要有「无法解析」节
    blank = fitz.open()
    blank.new_page(width=595, height=420)
    blank.save(f'{inv}/10 月 1 日/scan_无文本层.pdf')
    blank.close()
    # 用例9:单日票数超过 20,合计行 SUM 必须盖住全部数据行(旧 bug:固定 D4:D23 少算)
    os.makedirs(f'{inv}/10 月 3 日')
    for i in range(21):
        make_pdf(f'{inv}/10 月 3 日/10.3钱七{i:02d}26442000011334973{i:03d}.pdf',
                 f'26442000011334973{i:03d}', '2026年10月03日', '50')
    # 用例10:字典外人员进汇总表,垫底且工资号/职名留空
    make_pdf(f'{inv}/10 月 2 日/10.2孙九26442000011334972006.pdf',
             '26442000011334972006', '2026年10月02日', '55')

    out = os.path.join(tmp, 'out.xlsx')
    report = os.path.join(tmp, 'report.md')
    summary = os.path.join(tmp, 'summary.xlsx')
    subprocess.run([sys.executable, BUILD, '--invoice-dir', inv, '--dict-xlsx', dict_x,
                    '--out', out, '--report', report, '--summary-out', summary],
                   check=True, capture_output=True)
    rep = open(report, encoding='utf-8').read()

    wb = openpyxl.load_workbook(out)
    ws2 = wb['2026.10.2']
    ws3 = wb['2026.10.3']
    swb = openpyxl.load_workbook(summary)
    sws = swb['餐补汇总表']

    def users_of(no):
        return next((str(ws2.cell(row=r, column=7).value) for r in range(4, 24)
                     if ws2.cell(row=r, column=2).value == no), '')

    def srow_of(name):
        return next((r for r in range(4, 44) if sws.cell(row=r, column=4).value == name), None)

    liwang = users_of('26442000011322630931')

    total_r = next((r for r in range(4, 50) if sws.cell(row=r, column=2).value == '总 计'), None)
    checks = [
        ('查重保留人名多的那张',
         '保留 `10 月 2 日/b 张三26442000011334972541.pdf`' in rep
         and '剔除 `10 月 2 日/a_26442000011334972541.pdf`' in rep),
        ('替代记录入库(10.2 共 10 张 796/700)', '| 2026.10.2 | 10 | 796 | 700 |' in rep),
        ('全角逗号日期解析出两人(使用人=李四、王五)', liwang == '李四、王五'),
        ('空号票不互相误判(10.1 共 2 张)', '| 2026.10.1 | 2 | 104 | 100 |' in rep),
        ('同人同天冲突列出(2026.10.2 张三 ×3)', '2026.10.2 张三' in rep),
        ('班组前缀不粘人(使用人=李四)',
         users_of('26442000011334972001') == '李四'),
        ('缺日日期+噪音+连写按字典拆分(张三、李四、王五)',
         users_of('26442000011334972002') == '张三、李四、王五'),
        ('三字连写拆分(欧阳锋、耿楠楠)',
         users_of('26442000011334972003') == '欧阳锋、耿楠楠'),
        ('前导数字「925」不粘人(使用人=赵六)',
         users_of('26442000011334972004') == '赵六'),
        ('日期后缀「号」不粘人且不误报字典外(使用人=钱七)',
         users_of('26442000011334972005') == '钱七' and '号钱七' not in rep),
        ('无文本层 PDF 进报告「无法解析」节',
         '## 无法解析的 PDF' in rep and 'scan_无文本层.pdf' in rep),
        ('超20张时SUM覆盖全部数据行',
         next((ws3.cell(row=r, column=4).value for r in range(4, 40)
               if ws3.cell(row=r, column=2).value == '合计'), '')
         == '=SUM(D4:D24)'),
        ('汇总表人员按字典序(第1人=张三)',
         sws.cell(row=4, column=4).value == '张三'),
        ('当班天数按日期去重(赵六2天、钱七3天含21张同天票只算1天)',
         srow_of('赵六') and sws.cell(row=srow_of('赵六'), column=6).value == 2
         and srow_of('钱七') and sws.cell(row=srow_of('钱七'), column=6).value == 3),
        ('字典外人员垫底且工资号/职名留空(孙九第8人)',
         srow_of('孙九') == 11 and sws.cell(row=11, column=3).value is None
         and sws.cell(row=11, column=5).value is None),
        ('金额列=天数×50公式、总计行SUM盖住补足空行',
         sws.cell(row=4, column=7).value == '=F4*50'
         and total_r is not None
         and sws.cell(row=total_r, column=7).value == f'=SUM(G4:G{total_r - 1})'),
        ('内嵌工资号字典 sheet 供 VLOOKUP(隐藏)',
         '工资号' in swb.sheetnames and swb['工资号'].sheet_state == 'hidden'
         and swb['工资号']['A1'].value == '张三'
         and sws.cell(row=4, column=3).value == '=VLOOKUP(D4,工资号!A:B,2,0)'),
        ('报告有汇总表对账节(11人天550元 vs 实报1850元)',
         '## 汇总表对账' in rep and '总计 550 元' in rep
         and '明细实报合计：1850 元' in rep and '同人同天重复计 1300 元' in rep),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(('  PASS ' if ok else '  FAIL ') + name)
    print('PASS: 回归用例全部通过' if not failed else f'FAIL: {len(failed)} 项未通过')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
