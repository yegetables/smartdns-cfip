#!/usr/bin/env python3
"""cf-optimize.py 和 bestcf-optimize.py 共用的 cfdata 调用/结果处理逻辑"""

import os
import re
import subprocess
import time


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


def run_cfdata(cfdata_path, root, log_path, nsb_args, move_dir, move_prefix, label, header_tag, poll_interval=20):
    """后台执行 cfdata，监控日志直到完成，然后把 ip.csv/ip.txt 移到 move_dir/{move_prefix}{name}。"""
    log(f"{label} 启动 cfdata (日志: {os.path.basename(log_path)})")

    with open(log_path, "a", encoding="utf-8") as lf:
        lf.write(f"\n========== {header_tag} {time.strftime('%Y-%m-%d %H:%M:%S')} ==========\n")

    cmd = [
        cfdata_path,
        "-cli", "-mode=nsb", "-dns=223.5.5.5",
        "-fields=ipport,loc,latency,speed",
        "-nocolor", "-nsbqualified",
    ] + nsb_args

    lf_handle = open(log_path, "ab")
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=lf_handle,
        stderr=subprocess.STDOUT,
        cwd=root,
    )
    proc.stdin.write(b"y\n")
    proc.stdin.flush()
    proc.stdin.close()

    prev_tail = []
    idle = 0
    log(f"      PID: {proc.pid}")
    log(f"      每 {poll_interval}s 检查进度...")

    while True:
        time.sleep(poll_interval)
        if proc.poll() is not None:
            proc.wait()
            lf_handle.close()
            log(f"      ✅ cfdata 已完成")
            break

        cur_tail = tail(log_path, 10)
        if cur_tail == prev_tail:
            idle += 1
            still_alive = proc.poll() is None
            alive_msg = "进程仍存活" if still_alive else "⚠️ 进程已退出"
            log(f"      ⚠️ 超过 {poll_interval}s 无新输出 (第{idle}次) — {alive_msg}")
            if not still_alive:
                proc.wait()
                lf_handle.close()
                log(f"      ✅ cfdata 已完成 (进程退出后确认)")
                break
            time.sleep(5)
        else:
            idle = 0
        prev_tail = cur_tail

    for name in ("ip.csv", "ip.txt"):
        src = os.path.join(root, name)
        if os.path.exists(src):
            dst = os.path.join(move_dir, f"{move_prefix}{name}")
            os.replace(src, dst)
            log(f"      {name} → {move_prefix}{name}")


def sort_dedup_top(result_file, speedlimit):
    """读取达标结果文件，按速度降序排序，按 ip:port 去重，返回前 speedlimit 条。"""
    if not os.path.exists(result_file):
        return []

    with open(result_file, "r", encoding="utf-8") as f:
        lines = [l.strip().strip("﻿") for l in f if l.strip() and "MB/s" in l]

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

    return merged[:speedlimit]


def extract_ips(lines):
    """从 ip:port#备注 风格的行中提取去重后的纯 IP 列表（保持原顺序）。"""
    ips = []
    for line in lines:
        ip = line.split("#")[0].split(":")[0]
        if ip and ip not in ips:
            ips.append(ip)
    return ips


def write_lines(path, lines):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def read_lines(path):
    """读取文件，去 BOM/去首尾空白，跳过空行，返回 list。"""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip().strip("﻿") for line in f if line.strip()]


def filter_by_port(lines, port):
    """从 ip:port#备注 风格的行中筛出端口等于 port 的行。"""
    target = str(port)
    result = []
    for line in lines:
        head = line.split("#")[0]
        p = head.rsplit(":", 1)[-1] if ":" in head else ""
        if p == target:
            result.append(line)
    return result


def write_preferred_ipv4(edgetunnel_path, out_path, port=443):
    """从 edgetunnel_path 中筛出指定端口的行，提取纯 IP 写入 out_path，返回 IP 数量。"""
    lines = read_lines(edgetunnel_path)
    filtered = filter_by_port(lines, port)
    ips = extract_ips(filtered)
    write_lines(out_path, ips)
    return len(ips)


def merge_with_previous(previous_edgetunnel_path, new_source_path, cap, merged_src_path):
    """合并上次 edgetunnel.txt（全部）+ new_source_path 前 cap 行，写入 merged_src_path。

    返回 (previous_used, new_added, total)。
    """
    with open(merged_src_path, "w", encoding="utf-8") as out:
        previous_used = False
        if os.path.exists(previous_edgetunnel_path):
            with open(previous_edgetunnel_path, "r", encoding="utf-8") as f:
                content = f.read()
            if content.strip():
                out.write(content)
                previous_used = True

        new_added = 0
        if os.path.exists(new_source_path):
            with open(new_source_path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= cap:
                        break
                    out.write(line)
                    new_added += 1

    total = 0
    with open(merged_src_path, "r", encoding="utf-8") as f:
        for _ in f:
            total += 1

    return previous_used, new_added, total
