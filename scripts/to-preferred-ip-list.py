#!/usr/bin/env python3
"""
从 ip.txt 提取纯 IP 列表（与 ip.txt 顺序一致）

注意: preferred-ipv4.txt 惯例使用 443 端口的结果。如果用 8443 等端口生成，需确认是否合适。

用法:
  python to-preferred-ip-list.py                # 读取 ip.txt，输出 preferred-ipv4.txt
  python to-preferred-ip-list.py ip.txt         # 指定输入文件
  python to-preferred-ip-list.py ip.txt -o out.txt
"""
import sys, re

src = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else 'ip.txt'
out = 'preferred-ipv4.txt'
if '-o' in sys.argv:
    i = sys.argv.index('-o')
    if i + 1 < len(sys.argv):
        out = sys.argv[i + 1]

ips = []
with open(src) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        ip = line.split(':')[0]  # "IP:PORT#..." → IP
        if ip:
            ips.append(ip)

with open(out, 'w') as f:
    f.write('\n'.join(ips) + '\n')

print(f'{out}  ({len(ips)} 条)')
