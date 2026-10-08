# -*- coding: utf-8 -*-
"""Build the offline, replaceable cover illustrations from theme geometry.

The 100×100 icon set remains an independent semantic fallback. These larger
320×250 compositions share lighting, projection and line-weight, while the five
most common report topics have purpose-drawn technical geometry.
"""
from pathlib import Path
import argparse
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / 'assets' / 'svg'
OUT_DIR = ROOT / 'assets' / 'theme'

CUSTOM = {
    'doorhandle': '''
      <path d="M13 48 Q17 39 29 38 L76 32 Q89 31 91 41 L92 56 Q91 66 80 67 L26 73 Q13 74 12 63 Z" fill="#FFFBF4"/>
      <path d="M22 50 Q26 44 34 43 L74 38 Q83 37 85 44 L85 51 Q84 55 77 56 L32 62 Q25 62 22 56 Z" fill="#FFD8A8" fill-opacity=".55"/>
      <path d="M30 44 L74 39 Q80 39 80 44 L78 49 Q76 52 72 52 L33 57 Q28 57 27 53 Q26 48 30 44 Z" fill="#FFFBF4"/>
      <path d="M29 54 Q47 52 74 48 M32 44 L35 55 M75 39 L74 49" stroke-width="1.25" opacity=".7"/>
      <path d="M19 65 Q44 66 83 59" stroke-width="1.1" opacity=".65"/>
      <circle cx="86" cy="61" r="1.3" fill="#F5820B" stroke="none"/>''',
    'engine': '''
      <path d="M13 37 L30 28 L77 28 L88 38 L88 72 L76 81 L28 81 L13 72 Z"/>
      <path d="M13 37 L28 47 L77 47 L88 38 M28 47 L28 81 M77 47 L77 81"/>
      <path d="M24 27 L30 19 L69 19 L77 28 M31 19 L31 14 M42 19 L42 14 M53 19 L53 14 M64 19 L64 14"/>
      <path d="M35 54 L65 54 L72 60 L72 69 L65 75 L35 75 L32 69 L32 60 Z"/>
      <circle cx="52" cy="64" r="8"/><circle cx="52" cy="64" r="2"/>
      <path d="M88 48 L95 48 L95 68 L88 68 M6 47 L13 47 M6 62 L13 62 M22 35 L77 35" stroke-width="1.2" opacity=".7"/>''',
    'screen': '''
      <path d="M11 19 L82 13 Q90 13 91 21 L94 71 Q94 78 86 80 L19 87 Q11 88 10 79 L7 29 Q6 22 11 19 Z"/>
      <path d="M16 26 L81 21 L84 70 L19 77 Z"/>
      <path d="M19 64 L83 58 M42 75 L43 84 M64 73 L66 82 M31 87 L76 83"/>
      <path d="M23 34 L42 32 M23 42 L33 41 M53 30 L74 28 M53 39 L75 37 M26 53 L74 49" stroke-width="1.2" opacity=".7"/>
      <circle cx="87" cy="27" r="1.4"/>''',
    'seat': '''
      <path d="M31 13 Q31 7 38 7 L60 9 Q67 10 67 17 L65 29 L34 27 Z"/>
      <path d="M28 29 Q28 24 34 25 L67 28 Q73 29 73 36 L70 66 Q69 73 62 75 L31 69 Q25 67 25 59 Z"/>
      <path d="M31 69 L62 75 L82 67 Q88 66 91 72 L92 78 Q92 83 86 85 L53 93 L24 85 Q17 83 18 77 Q19 72 31 69 Z"/>
      <path d="M25 77 L53 85 L89 76 M62 75 L62 42 M33 34 L63 38 M26 59 L61 67"/>
      <path d="M32 87 L28 97 M80 87 L84 96" stroke-width="1.3" opacity=".6"/>''',
    'ac': '''
      <path d="M8 29 L83 21 Q91 21 93 29 L94 59 Q94 66 87 67 L15 75 Q9 75 8 69 Z"/>
      <path d="M15 37 L86 30 L87 56 L16 65 Z M20 69 L82 62"/>
      <path d="M22 43 L80 37 M22 49 L80 43 M22 55 L80 49" stroke-width="1.5"/>
      <path d="M26 78 Q21 86 29 91 M46 76 Q39 87 47 94 M67 73 Q60 84 68 90" stroke-width="1.3" opacity=".65"/>
      <circle cx="84" cy="61" r="1.5"/>''',
}


def geometry(stem):
    if stem in CUSTOM:
        return CUSTOM[stem]
    icon = ICON_DIR / f'icon-{stem}.svg'
    if not icon.is_file():
        raise FileNotFoundError(icon)
    root = ET.parse(icon).getroot()
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    # Only copy the known, local icon geometry. Root styling belongs to the
    # cover system; the original icon is left unchanged for small uses.
    inner = ''.join(ET.tostring(child, encoding='unicode') for child in root)
    inner = re.sub(r'\sxmlns(:\w+)?="[^"]+"', '', inner)
    return inner.replace('fill="#F5820B"', 'fill="#F7C788"')


def visual(stem):
    subject = geometry(stem)
    context = '''<g fill="none" stroke="#C4620A" stroke-linejoin="round" stroke-linecap="round">
    <path d="M88 74 Q140 22 234 21 Q282 22 308 51 L317 66 L106 83 Z" fill="#FFF7EC" fill-opacity=".52" stroke-width="1.4" opacity=".38"/>
    <path d="M104 82 L316 65 M109 82 L110 214 Q212 228 315 202 M313 67 L315 202" stroke-width="1.65" opacity=".46"/>
    <path d="M115 185 Q213 182 316 165 M121 217 Q216 218 308 196" stroke-width="1.2" opacity=".31"/>
    <path d="M250 24 L261 72" stroke-width="1.4" opacity=".3"/>
  </g>''' if stem == 'doorhandle' else ''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 250" role="img" aria-label="{stem} technical illustration">
  <defs>
    <radialGradient id="wash"><stop stop-color="#FFCF8C" stop-opacity=".34"/><stop offset="1" stop-color="#FFF7EC" stop-opacity="0"/></radialGradient>
    <linearGradient id="face" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#FFFBF4" stop-opacity=".7"/><stop offset=".65" stop-color="#FFD8A8" stop-opacity=".32"/><stop offset="1" stop-color="#F5820B" stop-opacity=".08"/></linearGradient>
    <filter id="blur"><feGaussianBlur stdDeviation="8"/></filter>
    <g id="subject" fill="url(#face)" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.1">{subject}</g>
  </defs>
  <ellipse cx="211" cy="119" rx="123" ry="105" fill="url(#wash)"/>
  {context}
  <g fill="none" stroke="#F5820B" stroke-width="1" opacity=".15">
    <path d="M32 211 L303 176 M55 229 L310 198 M95 236 L314 219 M88 72 L295 35 M119 52 L280 16"/>
    <path d="M67 175 Q172 226 310 153 M89 55 Q193 5 296 53" stroke-dasharray="3 6"/>
    <circle cx="224" cy="118" r="96" stroke-dasharray="2 8"/>
    <circle cx="224" cy="118" r="112" stroke-dasharray="1 11"/>
  </g>
  <ellipse cx="224" cy="209" rx="81" ry="12" fill="#C4620A" opacity=".16" filter="url(#blur)"/>
  <g transform="translate(84 12) scale(2.2)">
    <use href="#subject" transform="translate(5 7)" fill="none" stroke="#C4620A" opacity=".18" stroke-width="3.6"/>
    <use href="#subject" transform="translate(2 3)" fill="none" stroke="#FFB347" opacity=".52" stroke-width="3"/>
    <use href="#subject" stroke="#C4620A"/>
  </g>
  <g fill="#F5820B" opacity=".28"><circle cx="104" cy="182" r="2"/><circle cx="298" cy="53" r="2"/><circle cx="304" cy="166" r="2"/></g>
  <g fill="none" stroke="#F5820B" opacity=".2" stroke-width="1"><path d="M104 182h-27v15 M298 53h12v-16 M304 166h12v15"/></g>
</svg>
'''


def main():
    ap = argparse.ArgumentParser(description='Build or verify offline cover-theme SVG assets.')
    ap.add_argument('--check', action='store_true', help='verify generated assets without writing')
    args = ap.parse_args()
    if not args.check:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
    failures = []
    for icon in sorted(ICON_DIR.glob('icon-*.svg')):
        stem = icon.stem.removeprefix('icon-')
        dest = OUT_DIR / f'hero-{stem}.svg'
        content = visual(stem)
        ET.fromstring(content)  # Catch invalid SVG before writing.
        if args.check:
            if not dest.is_file() or dest.read_text(encoding='utf-8') != content:
                failures.append(dest.name)
        else:
            dest.write_text(content, encoding='utf-8')
            print(dest.name)
    if failures:
        ap.error('missing or stale visual assets: ' + ', '.join(failures))
    if args.check:
        print(f'OK: {len(list(ICON_DIR.glob("icon-*.svg")))} theme visuals match their sources')


if __name__ == '__main__':
    main()
