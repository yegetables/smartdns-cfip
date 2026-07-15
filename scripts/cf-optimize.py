#!/usr/bin/env python3
"""
CF IP 优选完整工作流
用法: python cf-optimize.py [端口号]

流程:
  1. 存档 edgetunnel.txt → old-edgetunnel.txt
  2. 合并 old-edgetunnel.txt + 端口 ALL.txt → 统一源文件
  3. 一次统一测速 (后台执行，日志监控)
  4. 排序去重取 top N → edgetunnel.txt
  5. 生成 ip.txt + preferred-ipv4.txt
  6. 清理中间文件
"""

import os
import re
import sys
import subprocess
import time

# ===== 配置 =====
PORT = sys.argv[1] if len(sys.argv) > 1 else "443"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUTS = os.path.join(ROOT, "outputs")
PORTS = os.path.join(ROOT, "ports")
CFDATA = os.path.join(ROOT, "cfdata-windows-amd64.exe")
INPUT_FILE = os.path.join(PORTS, PORT, "ALL.txt")
LOG = os.path.join(OUTPUTS, "cf-optimize.log")
MERGED_SRC = os.path.join(OUTPUTS, ".merged-source.txt")

SPEEDMIN = 3
SPEEDLIMIT = 10
SPEEDTEST = 8
RESULTLIMIT = 400


def log(msg):
    print(msg, flush=True)


def tail(filepath, n=10):
    """读取文件最后 n 行，不读入全部文件到内存。"""
    if not os.path.exists(filepath):
        return []
    with open(filepath, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        if size == 0:
            return []
        block = 1024
        data = []
        remaining = n
        pos = size
        while remaining > 0 and pos > 0:
            read_size = min(block, pos)
            pos -= read_size
            f.seek(pos)
            chunk = f.read(read_size)
            data.append(chunk)
            remaining -= chunk.count(b"\n")
        raw = b"".join(reversed(data))
        lines = raw.decode("utf-8", errors="replace").splitlines()
        return lines[-n:]


def run_cfdata(extra_args, step_label):
    """后台执行 cfdata，监控日志直到完成。"""
    log(f"[{step_label}] 启动 cfdata (日志: cf-optimize.log)")

    with open(LOG, "a", encoding="utf-8") as lf:
        lf.write(f"\n========== {step_label} {time.strftime('%Y-%m-%d %H:%M:%S')} ==========\n")

    cmd = [
        CFDATA,
        "-cli", "-mode=nsb", "-dns=223.5.5.5",
        "-fields=ipport,loc,latency,speed",
        "-nocolor", "-nsbqualified",
        f"-nsbspeedmin={SPEEDMIN}",
        f"-nsbspeedlimit={SPEEDLIMIT}",
        f"-nsbspeedtest={SPEEDTEST}",
        f"-nsbresultlimit={RESULTLIMIT}",
    ] + extra_args

    lf_handle = open(LOG, "ab")
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=lf_handle,
        stderr=subprocess.STDOUT,
        cwd=ROOT,
    )
    proc.stdin.write(b"y\n")
    proc.stdin.flush()
    proc.stdin.close()

    # 监控循环
    prev_tail = []
    idle = 0
    log(f"      PID: {proc.pid}")
    log(f"      每 20s 检查进度...")

    while True:
        time.sleep(20)
        if proc.poll() is not None:
            proc.wait()
            lf_handle.close()
            log(f"      ✅ cfdata 已完成")
            break

        cur_tail = tail(LOG, 10)
        if cur_tail == prev_tail:
            idle += 1
            log(f"      ⚠️ 超过 20s 无新输出 (第{idle}次)")
            time.sleep(5)
            if proc.poll() is not None:
                proc.wait()
                lf_handle.close()
                log(f"      ✅ cfdata 已完成 (空闲检测后)")
                break
        else:
            idle = 0
        prev_tail = cur_tail

    # 移动结果文件
    for name in ("ip.csv", "ip.txt"):
        src = os.path.join(ROOT, name)
        if os.path.exists(src):
            dst = os.path.join(OUTPUTS, f"{step_label}-{name}")
            os.replace(src, dst)
            log(f"      {name} → {step_label}-{name}")


# ===== 主流程 =====
def main():
    log("")
    log("=" * 44)
    log(f" CF IP 优选 — 端口 {PORT}")
    log(f" 速度下限: {SPEEDMIN}MB/s  保留: {SPEEDLIMIT} 个")
    log("=" * 44)
    log("")

    # ---- 步骤 1: 存档 ----
    log("[1/6] 存档 edgetunnel.txt")
    src = os.path.join(OUTPUTS, "edgetunnel.txt")
    if os.path.exists(src):
        dst = os.path.join(OUTPUTS, "old-edgetunnel.txt")
        import shutil
        shutil.copy2(src, dst)
        log("      → old-edgetunnel.txt")
    log("")

    # ---- 步骤 2: 合并源文件 ----
    log("[2/6] 合并源文件")
    with open(MERGED_SRC, "w", encoding="utf-8") as out:
        old_src = os.path.join(OUTPUTS, "old-edgetunnel.txt")
        if os.path.exists(old_src):
            with open(old_src, "r", encoding="utf-8") as f:
                out.write(f.read())
            log("      加入 old-edgetunnel.txt")

        if os.path.exists(INPUT_FILE):
            with open(INPUT_FILE, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= RESULTLIMIT:
                        break
                    out.write(line)
            log(f"      加入 {INPUT_FILE} (前 {RESULTLIMIT} 条)")

    count = 0
    with open(MERGED_SRC, "r") as f:
        for _ in f:
            count += 1
    log(f"      共 {count} 条")
    log("")

    # ---- 步骤 3: 统一测速 ----
    log("[3/6] 统一测速 (后台执行)")
    # 清空日志
    with open(LOG, "w") as f:
        f.write("")

    run_cfdata([
        f"-nsbfallbackport={PORT}",
        f"-nsbfile={MERGED_SRC}",
    ], "port-" + PORT)
    log("")

    # ---- 步骤 4: 排序去重 → edgetunnel.txt ----
    log("[4/6] 排序去重 → edgetunnel.txt")

    step_label = f"port-{PORT}"
    result_file = os.path.join(OUTPUTS, f"{step_label}-ip.txt")

    if os.path.exists(result_file):
        with open(result_file, "r", encoding="utf-8") as f:
            lines = [l.strip().strip("\ufeff") for l in f if l.strip() and "MB/s" in l]

        parsed = []
        for line in lines:
            m = re.search(r"([\d.]+)MB/s$", line)
            if m:
                try:
                    parsed.append((float(m.group(1)), line))
                except ValueError:
                    pass

        parsed.sort(key=lambda x: x[0], reverse=True)

        seen = set()
        merged = []
        for speed, line in parsed:
            key = line.split("#")[0]
            if key not in seen:
                seen.add(key)
                merged.append(line)

        merged = merged[:SPEEDLIMIT]

        out_path = os.path.join(OUTPUTS, "edgetunnel.txt")
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(merged) + "\n")

        log(f"      edgetunnel.txt: {len(merged)} 个节点 (top {SPEEDLIMIT})")
        for l in merged:
            log(f"        {l}")
    else:
        log("      ⚠️ 未生成结果文件")
    log("")

    # ---- 步骤 5: 生成 ip.txt + preferred-ipv4.txt ----
    log("[5/6] 生成 ip.txt + preferred-ipv4.txt")
    edgetunnel = os.path.join(OUTPUTS, "edgetunnel.txt")
    if os.path.exists(edgetunnel):
        with open(edgetunnel, "r", encoding="utf-8") as f:
            lines = [l.strip().strip("\ufeff") for l in f if l.strip()]

        with open(os.path.join(OUTPUTS, "ip.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        log(f"      ip.txt: {len(lines)} 条")

        ips = []
        for line in lines:
            ip = line.split("#")[0].split(":")[0]
            if ip not in ips:
                ips.append(ip)
        with open(os.path.join(OUTPUTS, "preferred-ipv4.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(ips) + "\n")
        log(f"      preferred-ipv4.txt: {len(ips)} 个 IP")
    log("")

    # ---- 步骤 6: 清理 ----
    log("[6/6] 清理中间文件")
    for f in [MERGED_SRC, os.path.join(OUTPUTS, "old-edgetunnel.txt"),
              os.path.join(OUTPUTS, "old-edgetunnel.csv")]:
        if os.path.exists(f):
            os.remove(f)
    log("      done")
    log("")

    log("=" * 44)
    log(" ✅ 完成")
    log("=" * 44)
    log(f" outputs/edgetunnel.txt       — 合并结果 (top {SPEEDLIMIT})")
    log(f" outputs/port-{PORT}.csv       — 测速原始数据")
    log(f" outputs/ip.txt               — 合并版 txt")
    log(f" outputs/preferred-ipv4.txt   — 纯 IP 列表")
    log(f" outputs/cf-optimize.log      — 详细日志")
    log("=" * 44)


if __name__ == "__main__":
    main()
