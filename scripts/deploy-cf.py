#!/usr/bin/env python3
"""
部署 CF 优选结果到 pve.fnos
用法: python deploy-cf.py

将 outputs/ 下的 preferred-ipv4.txt 和 edgetunnel.txt
scp 到远程服务器，git push 后重启 smartdns
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUTS = os.path.join(ROOT, "outputs")
REMOTE = "pve.fnos"
REMOTE_BASE = "/home/ajian/compose-all/1panel-compose/smartdns-cfip"

SRC_IPS = os.path.join(OUTPUTS, "preferred-ipv4.txt")
DST_IPS = f"{REMOTE}:{REMOTE_BASE}/cloudflare-ips/preferred-ipv4.txt"
SRC_EDGE = os.path.join(OUTPUTS, "edgetunnel.txt")
DST_EDGE = f"{REMOTE}:{REMOTE_BASE}/others-preferred-cfip/edgetunnel.txt"


def log(msg):
    print(msg, flush=True)


def run(cmd, timeout=60):
    """执行命令，返回退出码。"""
    result = subprocess.run(cmd, shell=True, timeout=timeout,
                            capture_output=True, text=True)
    if result.stdout:
        log(result.stdout.rstrip())
    if result.stderr:
        # 过滤无害的 SSH warning
        for line in result.stderr.splitlines():
            if "remote port forwarding failed" not in line:
                log(line)
    return result.returncode


def main():
    log("=" * 44)
    log(f" 部署 CF 优选 → {REMOTE}")
    log("=" * 44)

    # 检查本地文件是否存在且非空
    all_empty = True
    for f in (SRC_IPS, SRC_EDGE):
        if not os.path.exists(f):
            log(f"❌ 缺少文件: {f}")
            log("   请先运行 python scripts/cf-optimize.py")
            sys.exit(1)
        if os.path.getsize(f) > 0:
            all_empty = False

    if all_empty:
        log("")
        log("⚠️ 两个源文件都为空！终止部署。")
        log("   请先运行 python scripts/cf-optimize.py 生成有效结果。")
        sys.exit(1)

    log("")

    # 统一换行符为 LF
    log("[pre] dos2unix 转换换行符")
    for f in (SRC_IPS, SRC_EDGE):
        rc = run(f'dos2unix "{f}"', timeout=10)
        if rc != 0:
            log(f"  ⚠️ dos2unix 失败: {f}")
    log("")

    log("[1/4] scp preferred-ipv4.txt")
    rc = run(f'scp "{SRC_IPS}" "{DST_IPS}"')
    if rc != 0:
        sys.exit(rc)

    log("[2/4] scp edgetunnel.txt")
    rc = run(f'scp "{SRC_EDGE}" "{DST_EDGE}"')
    if rc != 0:
        sys.exit(rc)

    log("[3/4] git add + commit")
    run(f'ssh {REMOTE} "cd {REMOTE_BASE} && git add -A && git commit -m \'update cf ips\'"', timeout=30)

    log("       git push")
    rc = run(f'ssh {REMOTE} "cd {REMOTE_BASE} && git push"', timeout=30)

    log("[4/4] docker restart smartdns")
    rc = run(f'ssh {REMOTE} "docker restart smartdns"')
    if rc != 0:
        sys.exit(rc)

    log("")
    log("=" * 44)
    log(" ✅ 部署完成")
    log("=" * 44)


if __name__ == "__main__":
    main()
