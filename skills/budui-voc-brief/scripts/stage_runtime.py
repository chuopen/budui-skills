# -*- coding: utf-8 -*-
"""将运行脚本与全部必需 assets 整体复制到隔离执行目录。"""
import argparse
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(description='创建可独立运行的 VOC 简报运行目录')
    ap.add_argument('--out', required=True, help='不存在的目标目录')
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    if os.path.exists(out):
        print(f'[拒绝覆盖] 目标目录已存在：{out}', file=sys.stderr)
        return 2
    os.makedirs(out)
    shutil.copytree(os.path.join(ROOT, 'scripts'), os.path.join(out, 'scripts'), ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(os.path.join(ROOT, 'assets'), os.path.join(out, 'assets'))
    shutil.copy2(os.path.join(ROOT, 'manifest.json'), os.path.join(out, 'manifest.json'))
    print(f'OK: staged runtime -> {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
