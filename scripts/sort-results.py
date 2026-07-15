#!/usr/bin/env python3
"""
CFData-WEB 测速结果排序/筛选/输出
用法:
  python sort-results.py ip.csv                # 表格显示全部
  python sort-results.py ip.csv 1              # 只显示 > 1 MB/s
  python sort-results.py ip.csv 1 --ip         # 只输出 IP 列表（方便复制）
  python sort-results.py ip.csv 1 --csv        # 输出排序后的新 CSV
  python sort-results.py ip.csv 1 --csv out.csv
"""
import csv
import re
import sys
from pathlib import Path

# ── 解析参数 ──────────────────────────────────
args = sys.argv[1:]
if not args:
    print(__doc__.strip())
    sys.exit(0)

input_file = args[0]
min_speed = 0.0
output_mode = 'table'   # table | ip-only | csv
output_path = None

for a in args[1:]:
    if a in ('--ip', '-i'):
        output_mode = 'ip-only'
    elif a in ('--csv', '-c'):
        output_mode = 'csv'
    elif a.startswith('--csv='):
        output_mode = 'csv'
        output_path = a.split('=', 1)[1]
    elif a.startswith('-'):
        print(f'未知参数: {a}')
        sys.exit(1)
    else:
        try:
            min_speed = float(a)
        except ValueError:
            print(f'无法解析参数: {a}')
            sys.exit(1)

# ── 读取 & 排序 ────────────────────────────────
results = []
with open(input_file, 'r', encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    headers = next(reader)
    speed_idx = 7  # 下载速度 列

    for row in reader:
        if len(row) <= speed_idx:
            continue
        speed_str = row[speed_idx].strip()
        if speed_str in ('', '测速失败'):
            continue
        m = re.match(r'([\d.]+)\s*MB/s', speed_str)
        if m:
            s = float(m.group(1))
            if s > min_speed:
                results.append((s, row))

results.sort(key=lambda x: x[0], reverse=True)

# ── 输出 ───────────────────────────────────────
if output_mode == 'ip-only':
    for _, row in results:
        ip = row[0].strip()
        print(ip)
    sys.exit(0)

if output_mode == 'csv':
    if output_path:
        f_out = open(output_path, 'w', newline='', encoding='utf-8')
    else:
        f_out = None  # stdout
    writer = csv.writer(f_out or sys.stdout)
    writer.writerow(headers)
    for _, row in results:
        writer.writerow(row)
    if f_out:
        f_out.close()
        print(f'已写入 {output_path} ({len(results)} 条)')
    sys.exit(0)

# ── table 模式 ────────────────
print(f'文件: {Path(input_file).name}')
print(f'阈值: > {min_speed} MB/s')
print(f'命中: {len(results)} 条')
if len(results) == 0:
    sys.exit(0)
print('=' * 100)
hdr = f'{"速度":>10} | {"IP地址":>20} | {"延迟":>8} | {"地区":>12} | {"城市":>16} | ASN组织'
print(hdr)
print('-' * 10 + '-+-' + '-' * 20 + '-+-' + '-' * 8 + '-+-' + '-' * 12 + '-+-' + '-' * 16 + '-+-' + '-' * 30)

for s, row in results:
    ip = row[0].strip()
    lat = row[6].strip() if len(row) > 6 else ''
    loc = row[12].strip() if len(row) > 12 else ''
    city = row[13].strip() if len(row) > 13 else ''
    org = row[15].strip() if len(row) > 15 else ''
    print(f'{s:>8.2f}MB/s | {ip:>20} | {lat:>8} | {loc:>12} | {city:>16} | {org}')
