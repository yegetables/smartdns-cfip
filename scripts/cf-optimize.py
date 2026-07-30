#!/usr/bin/env python3
"""
CF IP 优选完整工作流
用法: python cf-optimize.py [端口号]

流程:
  1. 合并 上次 edgetunnel.txt + 端口 ALL.txt → 统一源文件
  2. 一次统一测速 (后台执行，日志监控)
  3. 排序去重取 top N → edgetunnel.txt
  4. 生成 ip.txt + preferred-ipv4.txt（仅443端口）
  5. 清理中间文件
"""

import os
import sys

import cfrunner
from cfrunner import log

# ===== 配置 =====
PORT = sys.argv[1] if len(sys.argv) > 1 else "443"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUTS = os.path.join(ROOT, "outputs")
PORTS = os.path.join(ROOT, "ports")
CFDATA = os.path.join(ROOT, "cfdata-windows-amd64.exe")
INPUT_FILE = os.path.join(PORTS, PORT, "ALL.txt")
LOG = os.path.join(OUTPUTS, "cf-optimize.log")
MERGED_SRC = os.path.join(OUTPUTS, ".merged-source.txt")
EDGETUNNEL = os.path.join(OUTPUTS, "edgetunnel.txt")

SPEEDMIN = 3
SPEEDLIMIT = 10
SPEEDTEST = 8
RESULTLIMIT = 400


# ===== 主流程 =====
def main():
    log("")
    log("=" * 44)
    log(f" CF IP 优选 — 端口 {PORT}")
    log(f" 速度下限: {SPEEDMIN}MB/s  保留: {SPEEDLIMIT} 个")
    log("=" * 44)
    log("")

    # ---- 步骤 1: 合并源文件 ----
    log("[1/5] 合并源文件（上次 edgetunnel.txt + ALL.txt）")
    previous_used, new_added, total = cfrunner.merge_with_previous(
        EDGETUNNEL, INPUT_FILE, RESULTLIMIT, MERGED_SRC
    )
    if previous_used:
        log("      加入上次 edgetunnel.txt")
    if new_added:
        log(f"      加入 {INPUT_FILE} (前 {new_added} 条)")
    log(f"      共 {total} 条")
    log("")

    # ---- 步骤 2: 统一测速 ----
    log("[2/5] 统一测速 (后台执行)")
    with open(LOG, "w") as f:
        f.write("")

    step_label = f"port-{PORT}"
    cfrunner.run_cfdata(
        CFDATA, ROOT, LOG,
        nsb_args=[
            f"-nsbspeedmin={SPEEDMIN}",
            f"-nsbspeedlimit={SPEEDLIMIT}",
            f"-nsbspeedtest={SPEEDTEST}",
            f"-nsbresultlimit={RESULTLIMIT}",
            f"-nsbfallbackport={PORT}",
            f"-nsbfile={MERGED_SRC}",
        ],
        move_dir=OUTPUTS,
        move_prefix=f"{step_label}-",
        label=f"[{step_label}]",
        header_tag=step_label,
    )
    log("")

    # ---- 步骤 3: 排序去重 → edgetunnel.txt ----
    log("[3/5] 排序去重 → edgetunnel.txt")

    result_file = os.path.join(OUTPUTS, f"{step_label}-ip.txt")

    if os.path.exists(result_file):
        merged = cfrunner.sort_dedup_top(result_file, SPEEDLIMIT)

        cfrunner.write_lines(EDGETUNNEL, merged)

        log(f"      edgetunnel.txt: {len(merged)} 个节点 (top {SPEEDLIMIT})")
        for l in merged:
            log(f"        {l}")
    else:
        log("      ⚠️ 未生成结果文件")
    log("")

    # ---- 步骤 4: 生成 ip.txt + preferred-ipv4.txt ----
    log("[4/5] 生成 ip.txt + preferred-ipv4.txt")
    if os.path.exists(EDGETUNNEL):
        lines = cfrunner.read_lines(EDGETUNNEL)
        cfrunner.write_lines(os.path.join(OUTPUTS, "ip.txt"), lines)
        log(f"      ip.txt: {len(lines)} 条")

        n = cfrunner.write_preferred_ipv4(EDGETUNNEL, os.path.join(OUTPUTS, "preferred-ipv4.txt"), port=443)
        log(f"      preferred-ipv4.txt: {n} 个 IP (仅443端口)")
    log("")

    # ---- 步骤 5: 清理 ----
    log("[5/5] 清理中间文件")
    if os.path.exists(MERGED_SRC):
        os.remove(MERGED_SRC)
    log("      done")
    log("")

    log("=" * 44)
    log(" ✅ 完成")
    log("=" * 44)
    log(f" outputs/edgetunnel.txt       — 合并结果 (top {SPEEDLIMIT})")
    log(f" outputs/port-{PORT}.csv       — 测速原始数据")
    log(f" outputs/ip.txt               — 合并版 txt")
    log(f" outputs/preferred-ipv4.txt   — 纯 IP 列表 (仅443端口)")
    log(f" outputs/cf-optimize.log      — 详细日志")
    log("=" * 44)


if __name__ == "__main__":
    main()
