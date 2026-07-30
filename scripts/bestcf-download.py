#!/usr/bin/env python3
"""
从 outputs/bestcf-tmp/download-list.txt 逐行下载文件到 raw/ 目录
使用 aria2c -c 断点续传，重复运行可继续未完成的下载

对 raw.githubusercontent.com 的失败 URL 会自动通过 gh-proxy.com 重试一次。

用法: python bestcf-download.py
"""

import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BESTCF_DIR = os.path.join(ROOT, "outputs", "bestcf-tmp")
DOWNLOAD_LIST = os.path.join(BESTCF_DIR, "download-list.txt")
RAW_DIR = os.path.join(BESTCF_DIR, "raw")


def sanitize(url):
    s = re.sub(r"^https?://", "", url)
    s = s.replace("/", "__")
    s = re.sub(r"[?&=]", "_", s)
    return f"{s}.txt"


def expected_filename(url, index):
    """返回 (basename, full_path)"""
    name = f"{index}_{sanitize(url)}"
    return name, os.path.join(RAW_DIR, name)


def file_is_ok(path):
    """文件存在且非空"""
    return os.path.exists(path) and os.path.getsize(path) > 0


def run_aria2c(url_entries, label=""):
    """
    运行 aria2c 批量下载。
    url_entries: list of (url, out_filename)
    返回 (成功数，失败列表)
    """
    if not url_entries:
        return 0, []

    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                     newline="\n", suffix=".txt",
                                     delete=False) as f:
        aria_input = f.name
        for url, out_name in url_entries:
            f.write(f"{url}\n")
            f.write(f"  out={out_name}\n")

    try:
        cmd = [
            "aria2c", "-c",
            "-i", aria_input,
            "-d", RAW_DIR,
            "-j", "16", "-x", "2", "-s", "1",
            "--retry-wait=2",
            "--max-tries=3",
            "--auto-file-renaming=false",
            "--console-log-level=warn",
            "--summary-interval=0",
        ]
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    finally:
        if os.path.exists(aria_input):
            os.remove(aria_input)

    # 判断每个文件是否成功
    ok_count = 0
    failed = []
    for url, out_name in url_entries:
        fpath = os.path.join(RAW_DIR, out_name)
        if file_is_ok(fpath):
            ok_count += 1
        else:
            failed.append((url, out_name))

    if label:
        print(f"  [{label}] 成功 {ok_count}/{len(url_entries)}，失败 {len(failed)}")
    if result.returncode != 0 and ok_count == len(url_entries):
        # aria2c 非零但所有文件都在 — 忽略
        pass

    return ok_count, failed


def main():
    if not os.path.exists(DOWNLOAD_LIST):
        print(f"未找到 {DOWNLOAD_LIST}")
        sys.exit(1)

    os.makedirs(RAW_DIR, exist_ok=True)

    with open(DOWNLOAD_LIST, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    if not urls:
        print("download-list.txt 为空")
        return

    print(f"共 {len(urls)} 个地址")

    # ---- 第一轮：原始 URL ----
    print("")
    print("第一轮：原始 URL 下载 (aria2c -c 断点续传)")
    first_entries = []
    skipped = 0
    for i, url in enumerate(urls, 1):
        _, fpath = expected_filename(url, i)
        if file_is_ok(fpath):
            skipped += 1
            continue
        first_entries.append((url, expected_filename(url, i)[0]))

    if skipped:
        print(f"  跳过 {skipped} 个已有文件")
    if first_entries:
        run_aria2c(first_entries, label="第一轮")
    else:
        print("  所有文件已存在，跳过第一轮")

    # ---- 第二轮：GitHub raw 失败 URL 通过 gh-proxy.com 重试 ----
    failed_github = []
    for i, url in enumerate(urls, 1):
        _, fpath = expected_filename(url, i)
        if file_is_ok(fpath):
            continue
        # 只重试 raw.githubusercontent.com 的 URL
        if "raw.githubusercontent.com" in url:
            proxy_url = f"https://gh-proxy.com/{url}"
            failed_github.append((proxy_url, expected_filename(url, i)[0]))

    if failed_github:
        print("")
        print(f"第二轮：{len(failed_github)} 个 GitHub raw URL 通过 gh-proxy.com 重试")
        run_aria2c(failed_github, label="第二轮")

    # ---- 最终汇总 ----
    print("")
    total = len(urls)
    succeeded = 0
    failed_list = []
    for i, url in enumerate(urls, 1):
        _, fpath = expected_filename(url, i)
        if file_is_ok(fpath):
            succeeded += 1
        else:
            failed_list.append((i, url))

    print(f"{'='*44}")
    print(f" 下载汇总: {succeeded}/{total} 成功")
    if failed_list:
        print(f" 失败 {len(failed_list)} 个:")
        for idx, url in failed_list:
            print(f"   #{idx} {url}")
    else:
        print(" ✅ 全部成功")
    print(f"{'='*44}")

    if failed_list:
        print("")
        print("提示：重新运行本脚本可重试失败的下载（已成功的文件不会重复下载）")
        sys.exit(1 if succeeded == 0 else 0)


if __name__ == "__main__":
    main()
