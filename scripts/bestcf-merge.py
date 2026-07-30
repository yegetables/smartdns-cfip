#!/usr/bin/env python3
"""
合并 outputs/bestcf-tmp/raw/ 目录内的下载文件 → merged-raw.txt
只读取 raw/ 子目录，不读取 bestcf-tmp/ 根目录下的其他文件（如 all-urls.txt、index.html）

用法: python bestcf-merge.py
"""

import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BESTCF_DIR = os.path.join(ROOT, "outputs", "bestcf-tmp")
RAW_DIR = os.path.join(BESTCF_DIR, "raw")
MERGED_FILE = os.path.join(BESTCF_DIR, "merged-raw.txt")

EXCLUDE_KEYWORDS = ("联通", "电信")


def sort_key(path):
    name = os.path.basename(path)
    m = re.match(r"(\d+)_", name)
    return int(m.group(1)) if m else float("inf")


def main():
    files = sorted(glob.glob(os.path.join(RAW_DIR, "*.txt")), key=sort_key)
    if not files:
        print(f"未在 {RAW_DIR} 找到任何文件")
        return

    lines = []
    excluded = 0
    for path in files:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        content = content.replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n")
        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue
            if any(kw in line for kw in EXCLUDE_KEYWORDS):
                excluded += 1
                continue
            lines.append(line)

    with open(MERGED_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    print(f"合并 {len(files)} 个文件 (raw/) → {MERGED_FILE} ({len(lines)} 行，排除 {excluded} 行含 {EXCLUDE_KEYWORDS})")


if __name__ == "__main__":
    main()
