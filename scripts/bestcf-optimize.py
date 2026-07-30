#!/usr/bin/env python3
"""
BestCF 聚合源测速工作流
源文件固定为 outputs/bestcf-tmp/merged-raw.txt
（由 bestcf-download.py 下载 + bestcf-merge.py 合并生成）

最终产出与流程1（cf-optimize.py）共享同一路径：
  outputs/edgetunnel.txt / outputs/ip.txt / outputs/preferred-ipv4.txt
两条流程谁后运行，谁的结果覆盖谁。

用法: python bestcf-optimize.py [端口号] [--no-merge] [--port <端口号>]
默认端口 443
--no-merge  不合并上次 edgetunnel.txt（默认行为，仅记录偏好）
--port      显式指定端口（与位置参数二选一）
--merge     显式合并上次 edgetunnel.txt（覆盖 --no-merge）

流程:
  1. 合并 上次 edgetunnel.txt + merged-raw.txt → 统一源文件
  2. 一次统一测速 (后台执行，日志监控)
  3. 排序去重取 top N → edgetunnel.txt
  4. 生成 ip.txt + preferred-ipv4.txt（仅443端口）
  5. 清理中间文件
"""

import os
import shutil
import sys

import cfrunner
from cfrunner import log

# ===== 配置 =====
# 解析参数：支持位置参数或 --port，跳过 -- 开头的选项
_raw_args = sys.argv[1:]
PORT = "443"
for _i, _a in enumerate(_raw_args):
    if _a == "--port" and _i + 1 < len(_raw_args):
        PORT = _raw_args[_i + 1]
        break
else:
    _non_option = [a for a in _raw_args if not a.startswith("--")]
    if _non_option:
        PORT = _non_option[0]
NO_MERGE = "--no-merge" in _raw_args
MERGE = "--merge" in _raw_args
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUTS = os.path.join(ROOT, "outputs")
BESTCF_DIR = os.path.join(OUTPUTS, "bestcf-tmp")
CFDATA = os.path.join(ROOT, "cfdata-windows-amd64.exe")
INPUT_FILE = os.path.join(BESTCF_DIR, "merged-raw.txt")
LOG = os.path.join(BESTCF_DIR, "bestcf-optimize.log")
MERGED_SRC = os.path.join(BESTCF_DIR, ".merged-source.txt")
EDGETUNNEL = os.path.join(OUTPUTS, "edgetunnel.txt")

DELAY = 500          # 扫描合格延迟 ms
RESULTLIMIT = 10000  # 扫描合格数量上限
SPEEDMIN = 5         # 速度达标下限 MB/s
SPEEDLIMIT = 20      # 最终保留数
SPEEDTEST = 8        # 测速并发线程数


def main():
    log("")
    log("=" * 44)
    log(f" BestCF 聚合源测速 — 端口 {PORT}")
    log(f" 扫描延迟: {DELAY}ms  扫描上限: {RESULTLIMIT}")
    log(f" 速度下限: {SPEEDMIN}MB/s  保留: {SPEEDLIMIT} 个  并发: {SPEEDTEST}")
    if NO_MERGE:
        log(" ⚠️ 不合并上次 edgetunnel.txt")
    log("=" * 44)
    log("")

    # ---- 步骤 1: 合并源文件 ----
    if not os.path.exists(INPUT_FILE):
        log(f"      ⚠️ 未找到 {INPUT_FILE}")
        log("      请先运行 bestcf-download.py + bestcf-merge.py 生成源文件")
        return

    if MERGE:
        log("[1/5] --merge 显式指定：合并上次 edgetunnel.txt + merged-raw.txt")
        previous_used, new_added, total = cfrunner.merge_with_previous(
            EDGETUNNEL, INPUT_FILE, RESULTLIMIT, MERGED_SRC
        )
        if previous_used:
            log("      加入上次 edgetunnel.txt")
        if new_added:
            log(f"      加入 {INPUT_FILE} (前 {new_added} 条)")
        log(f"      共 {total} 条")
    elif NO_MERGE:
        log("[1/5] 不使用上次 edgetunnel.txt，直接用 merged-raw.txt")
        shutil.copy2(INPUT_FILE, MERGED_SRC)
        log(f"      → {INPUT_FILE}")
    else:
        log("[1/5] 合并源文件（上次 edgetunnel.txt + merged-raw.txt）")
        previous_used, new_added, total = cfrunner.merge_with_previous(
            EDGETUNNEL, INPUT_FILE, RESULTLIMIT, MERGED_SRC
        )
        if previous_used:
            log("      加入上次 edgetunnel.txt")
        if new_added:
            log(f"      加入 {INPUT_FILE} (前 {new_added} 条)")
        log(f"      共 {total} 条")

    with open(LOG, "w") as f:
        f.write("")

    # ---- 步骤 2: 统一测速 ----
    log("[2/5] 统一测速 (后台执行)")
    cfrunner.run_cfdata(
        CFDATA, ROOT, LOG,
        nsb_args=[
            f"-nsbdelay={DELAY}",
            f"-nsbresultlimit={RESULTLIMIT}",
            f"-nsbspeedmin={SPEEDMIN}",
            f"-nsbspeedlimit={SPEEDLIMIT}",
            f"-nsbspeedtest={SPEEDTEST}",
            f"-nsbfallbackport={PORT}",
            f"-nsbfile={MERGED_SRC}",
        ],
        move_dir=BESTCF_DIR,
        move_prefix="bestcf-",
        label="[2/5]",
        header_tag="bestcf",
    )
    log("")

    # ---- 步骤 3: 排序去重 → edgetunnel.txt ----
    log("[3/5] 排序去重 → edgetunnel.txt")
    result_file = os.path.join(BESTCF_DIR, "bestcf-ip.txt")

    if os.path.exists(result_file):
        merged = cfrunner.sort_dedup_top(result_file, SPEEDLIMIT)

        cfrunner.write_lines(EDGETUNNEL, merged)

        log(f"      edgetunnel.txt: {len(merged)} 个节点 (top {SPEEDLIMIT})")
        for l in merged:
            log(f"        {l}")
    else:
        log("      ⚠️ 未生成结果文件（可能全部未达标，或代理环境下测速失败）")
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
    log(" outputs/edgetunnel.txt       — 合并结果 (与流程1共享，互相覆盖)")
    log(" outputs/bestcf-tmp/bestcf-ip.csv — 测速原始数据")
    log(" outputs/ip.txt               — 合并版 txt (与流程1共享)")
    log(" outputs/preferred-ipv4.txt   — 纯 IP 列表 (仅443端口，与流程1共享)")
    log(" outputs/bestcf-tmp/bestcf-optimize.log — 详细日志")
    log("=" * 44)


if __name__ == "__main__":
    main()
