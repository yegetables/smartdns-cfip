#!/usr/bin/env python3
"""
自动下载 CFData-WEB 二进制程序（适配当前平台架构）。
首次运行前执行：python scripts/setup.py

从 GitHub Releases 获取最新版：
  https://github.com/PoemMisty/CFData-WEB/releases
"""

import os
import sys
import platform
import urllib.request
import hashlib
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "PoemMisty/CFData-WEB"
API = f"https://api.github.com/repos/{REPO}/releases/latest"


def log(msg):
    print(msg, flush=True)


def detect_asset():
    """检测系统架构，返回 (asset_name, local_name)。"""
    machine = platform.machine().lower()
    system = platform.system().lower()

    if system == "windows":
        ext = ".exe"
        if machine in ("amd64", "x86_64"):
            return f"cfdata-windows-amd64{ext}", f"cfdata-windows-amd64{ext}"
        elif machine in ("arm64", "aarch64"):
            return f"cfdata-windows-arm64{ext}", f"cfdata-windows-arm64{ext}"
    elif system == "linux":
        ext = ""
        if machine in ("amd64", "x86_64"):
            return f"cfdata-linux-amd64{ext}", f"cfdata-linux-amd64{ext}"
        elif machine in ("arm64", "aarch64"):
            return f"cfdata-linux-arm64{ext}", f"cfdata-linux-arm64{ext}"
    elif system == "darwin":
        ext = ""
        if machine in ("amd64", "x86_64"):
            return f"cfdata-darwin-amd64{ext}", f"cfdata-darwin-amd64{ext}"
        elif machine in ("arm64", "aarch64"):
            return f"cfdata-darwin-arm64{ext}", f"cfdata-darwin-arm64{ext}"

    log(f"❌ 不支持的平台: {system}/{machine}")
    log("支持的平台：Windows/Linux/macOS (AMD64/ARM64)")
    sys.exit(1)


def get_latest_release():
    """从 GitHub API 获取最新 release 信息。"""
    log(f"查询最新版本: {API}")
    req = urllib.request.Request(API, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data["tag_name"], data["assets"]
    except Exception as e:
        log(f"  ⚠️ API 请求失败: {e}")
        log("  使用默认版本 v1.7.6")
        return "v1.7.6", []


def find_asset_url(assets, asset_name):
    """在 assets 列表中查找目标文件名。"""
    for a in assets:
        if a["name"] == asset_name:
            return a["browser_download_url"]
    return None


def download_file(url, dest, sha256_url=None):
    """下载文件到目标路径，可选校验 SHA256。"""
    log(f"  下载: {url}")
    try:
        urllib.request.urlretrieve(url, dest)
        size = os.path.getsize(dest)
        log(f"  已保存: {dest} ({size // 1024} KB)")

        # 下载 SHA256 校验
        if sha256_url:
            try:
                with urllib.request.urlopen(sha256_url, timeout=10) as resp:
                    expected = resp.read().decode().strip().split()[0]
                with open(dest, "rb") as f:
                    actual = hashlib.sha256(f.read()).hexdigest()
                if actual == expected:
                    log(f"  ✅ SHA256 校验通过")
                else:
                    log(f"  ⚠️ SHA256 不匹配 (expected={expected}, actual={actual})")
            except Exception as e:
                log(f"  ⚠️ SHA256 校验跳过: {e}")

        # Unix/macOS 加可执行权限
        if platform.system() != "Windows":
            os.chmod(dest, 0o755)

        return True
    except Exception as e:
        log(f"  ❌ 下载失败: {e}")
        return False


def main():
    log("=" * 44)
    log(" CFData-WEB 自动安装")
    log("=" * 44)
    log("")

    asset_name, local_name = detect_asset()
    log(f"系统: {platform.system()} / {platform.machine()}")
    log(f"目标: {asset_name}")
    log("")

    # 检查是否已存在
    local_path = os.path.join(ROOT, local_name)
    if os.path.exists(local_path):
        size = os.path.getsize(local_path)
        log(f"已存在: {local_name} ({size // 1024} KB)")
        log("如需覆盖请先删除: rm -f " + local_path)
        log("跳过下载。")
        log("")
        log("首次运行 cfdata 会自动下载 GeoLite2-ASN.mmdb 和 locations.json。")
        log("=" * 44)
        return

    # 获取最新 release
    tag, assets = get_latest_release()
    log(f"最新版本: {tag}")
    log("")

    # 查找下载 URL
    url = find_asset_url(assets, asset_name)
    sha_url = find_asset_url(assets, asset_name + ".sha256")

    if not url:
        # 构造默认 URL
        base = f"https://github.com/{REPO}/releases/download/{tag}"
        url = f"{base}/{asset_name}"
        sha_url = f"{base}/{asset_name}.sha256"
        log(f"  使用默认 URL (未在 API 中找到 assets 列表)")
    else:
        log(f"  从 release assets 中找到")

    log("")
    log(f"下载 {asset_name} ...")
    ok = download_file(url, local_path, sha_url)

    if ok:
        log("")
        log("✅ 安装完成")
        log("")
        log("首次运行 cfdata 会自动下载 GeoLite2-ASN.mmdb 和 locations.json。")
        log("现在可以直接使用: python scripts/cf-optimize.py")
    else:
        log("")
        log("❌ 安装失败")
        log(f"手动下载: {url}")
        log(f"保存到: {local_path}")

    log("=" * 44)


if __name__ == "__main__":
    main()
