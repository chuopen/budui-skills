# -*- coding: utf-8 -*-
"""海报 HTML → PNG 长图 + 单页 PDF（Chrome headless）

用法: python render_image.py --html 简报.html --out 输出前缀
产出: <out>.png / <out>.pdf
退出码: 0=全部成功 / 3=未找到浏览器，已跳过渲染（HTML 仍可用）

降级策略：找不到 Chrome/Edge 时不报错退出，而是打印 SKIPPED 标记并返回 3，
由调用方在交付说明里标注「本次交付 2 件：Excel、HTML；PNG/PDF 待补」，不打扰用户决策。
"""
import sys, os, re, subprocess, argparse, pathlib, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
C.setup_stdout()
C.add_site_packages()

EXIT_OK = 0
EXIT_NO_BROWSER = 3

CHROME_CANDIDATES = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    # 用户级安装目录（无管理员权限时常见）
    os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
    os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe'),
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
]
SCALE = 2
VIEW_W = 504

def find_chrome():
    for c in CHROME_CANDIDATES:
        if c and os.path.exists(c):
            return c
    for name in ('chrome', 'google-chrome', 'chromium', 'msedge'):
        p = shutil.which(name)
        if p:
            return p
    return None

def shot(chrome, url, out, height):
    cmd = [chrome, '--headless=new', '--disable-gpu', '--hide-scrollbars',
           f'--force-device-scale-factor={SCALE}', f'--screenshot={out}',
           f'--window-size={VIEW_W},{height}', url]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=240)
    return os.path.exists(out), r.stderr or ''


def content_bottom(png, scale=SCALE):
    """检测非背景行的最大 y，用于裁掉底部空白。"""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None
    im = Image.open(png).convert('RGB')
    a = np.array(im)
    bg = a[3, 3].astype(int)
    diff = np.abs(a.astype(int) - bg).sum(axis=2)
    rows = np.where((diff > 14).any(axis=1))[0]
    if not len(rows):
        return im.size[1]
    return min(int(rows.max()) + 16 * scale, im.size[1])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--html', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--no-pdf', action='store_true')
    a = ap.parse_args()

    chrome = find_chrome()
    if not chrome:
        print('SKIPPED: 未找到 Chrome/Edge，已跳过 PNG/PDF 渲染。')
        print('  HTML 海报已生成，可直接用浏览器打开或另存为图片。')
        print('  如需 PNG/PDF：安装 Chrome 或 Edge 后重跑本脚本即可。')
        return EXIT_NO_BROWSER
    html_path = pathlib.Path(a.html).resolve()
    out_base = pathlib.Path(a.out).resolve()
    stem = out_base.name
    if stem.lower().endswith(('.png', '.pdf')):
        stem = stem[:-4]
    out_png = out_base.parent / (stem + '.png')
    out_pdf = out_base.parent / (stem + '.pdf')
    out_png.parent.mkdir(parents=True, exist_ok=True)
    raw = out_png.with_name('_raw_' + out_png.name)
    for f in (raw, out_png, out_pdf):
        if f.exists():
            f.unlink()

    ok, err = shot(chrome, html_path.as_uri(), str(raw), 4600)
    if not ok:
        print(f'[PNG 渲染失败] {(err or "")[-400:]}')
        print('  已保留 HTML，可手动打开另存为图片。')
        return EXIT_NO_BROWSER

    bottom = content_bottom(str(raw))
    try:
        from PIL import Image
        im = Image.open(raw)
        if bottom and bottom < im.size[1]:
            im = im.crop((0, 0, im.size[0], bottom))
        im.save(out_png, optimize=True)
        H = im.size[1] // SCALE + 4
        print(f'PNG -> {out_png}  {im.size[0]}×{im.size[1]}  {os.path.getsize(out_png)/1024:.0f}KB')
    except ImportError:
        os.replace(raw, out_png)
        H = 3600
        print(f'PNG -> {out_png}（未装 Pillow，未裁剪）')
    if raw.exists():
        raw.unlink()

    if a.no_pdf:
        return EXIT_OK
    # 把内容高度注入 @page，保证 PDF 是单页长图
    src = html_path.read_text(encoding='utf-8')
    patched = re.sub(r'@page\s*\{[^}]*size:[^;}]*;', f'@page{{size:{VIEW_W}px {H}px;', src)
    if patched == src:
        patched = src.replace('@media print{', f'@media print{{@page{{size:{VIEW_W}px {H}px;margin:0}}', 1)
    tmp = html_path.with_name('_pdf_tmp_' + html_path.name)
    tmp.write_text(patched, encoding='utf-8')
    try:
        cmd = [chrome, '--headless=new', '--disable-gpu', '--no-pdf-header-footer',
               f'--print-to-pdf={out_pdf}', '--virtual-time-budget=8000', tmp.as_uri()]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=240)
        if out_pdf.exists():
            print(f'PDF -> {out_pdf}  {os.path.getsize(out_pdf)/1024:.0f}KB（单页 {VIEW_W}×{H}）')
        else:
            print(f'[PDF 渲染失败] {(r.stderr or "")[-300:]}')
    finally:
        if tmp.exists():
            tmp.unlink()
    return EXIT_OK

if __name__ == '__main__':
    sys.exit(main())
