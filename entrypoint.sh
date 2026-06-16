#!/bin/sh
# SmartDNS 入口脚本
# - 启动时下载 Cloudflare IP 段 + 生成配置
# - 每 6 小时: 刷新 CF IP 段 + 清理旧日志 + 维护 SQLite

DATA_DIR=/var/lib/smartdns
CF_DIR="${DATA_DIR}/cloudflare-ips"
CONF_FILE=/etc/smartdns/smartdns.conf
CONF_TEMPLATE=/etc/smartdns/smartdns.conf.template
LOG_DIR=/var/log/smartdns
DB_FILE="${DATA_DIR}/smartdns.db"

CF_IPV4_URL="https://www.cloudflare.com/ips-v4/"
CF_IPV6_URL="https://www.cloudflare.com/ips-v6/"

# ============================================
# 函数: HTTP 下载
# ============================================
http_get() {
    url="$1"
    if command -v curl >/dev/null 2>&1; then
        curl -sfk --max-time 15 "$url"
    else
        wget -qO- --timeout=15 --no-check-certificate "$url" 2>/dev/null
    fi
}

# ============================================
# 函数: 从文件提取纯 IP/CIDR 列表 (忽略 BOM、注释、空行)
# ============================================
read_ip_list() {
    file="$1"
    if [ -f "$file" ]; then
        grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(/[0-9]+)?$' "$file" 2>/dev/null \
            | sort -u | tr '\n' ',' | sed 's/,$//'
    fi
}

read_ipv6_list() {
    file="$1"
    if [ -f "$file" ]; then
        grep -E '^[0-9a-fA-F:]+(/[0-9]+)?$' "$file" 2>/dev/null \
            | sort -u | tr '\n' ',' | sed 's/,$//'
    fi
}

# ============================================
# 函数: 下载 Cloudflare IP 段
# ============================================
download_cf_ips() {
    echo "[entrypoint] 拉取 Cloudflare IP 段..."
    mkdir -p "$CF_DIR"

    # IPv4
    if http_get "$CF_IPV4_URL" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+' > "${CF_DIR}/cloudflare-ipv4.txt"; then
        echo "[entrypoint] IPv4: $(wc -l < "${CF_DIR}/cloudflare-ipv4.txt") 条"
    else
        echo "[entrypoint] IPv4 下载失败，保留旧文件"
        [ -f "${CF_DIR}/cloudflare-ipv4.txt" ] || echo "# Cloudflare IPv4" > "${CF_DIR}/cloudflare-ipv4.txt"
    fi

    # IPv6
    if http_get "$CF_IPV6_URL" | grep -oE '[0-9a-fA-F:]+/[0-9]+' > "${CF_DIR}/cloudflare-ipv6.txt"; then
        echo "[entrypoint] IPv6: $(wc -l < "${CF_DIR}/cloudflare-ipv6.txt") 条"
    else
        echo "[entrypoint] IPv6 下载失败，保留旧文件"
        [ -f "${CF_DIR}/cloudflare-ipv6.txt" ] || echo "# Cloudflare IPv6" > "${CF_DIR}/cloudflare-ipv6.txt"
    fi
}

# ============================================
# 函数: 生成 ip-rules 配置 (仅优选 IPv4，屏蔽 IPv6)
# ============================================
generate_ip_rules() {
    IPV4_LIST=$(read_ip_list "${CF_DIR}/preferred-ipv4.txt")
    IPV6_LIST=$(read_ipv6_list "${CF_DIR}/preferred-ipv6.txt")
    RULES=""

    # IPv4: CF A 记录 → 屏蔽 AAAA + 替换为优选 IPv4
    if [ -n "$IPV4_LIST" ]; then
        echo "[entrypoint] CF 优选 IPv4: ${IPV4_LIST}" >&2
        RULES="ip-rules ip-set:cloudflare-ipv4 -no-ipv6 -ip-alias ${IPV4_LIST}"
    else
        echo "[entrypoint] ⚠ preferred-ipv4.txt 为空，CF 优选未生效" >&2
        RULES="# preferred-ipv4.txt 为空，CF 优选未生效"
    fi

    # IPv6: CF AAAA 记录 → 屏蔽 (客户端拿不到 CF IPv6)
    if [ -n "$IPV6_LIST" ]; then
        echo "[entrypoint] CF IPv6 优选 (备用): ${IPV6_LIST}" >&2
        RULES="${RULES}
ip-rules ip-set:cloudflare-ipv6 -no-ipv6 -ip-alias ${IPV6_LIST}"
    else
        # 无优选 IPv6 时，仍然屏蔽 CF AAAA
        RULES="${RULES}
ip-rules ip-set:cloudflare-ipv6 -no-ipv6"
    fi

    echo "$RULES"
}

# ============================================
# 函数: 生成最终配置
# ============================================
generate_config() {
    echo "[entrypoint] 生成配置..."
    IP_RULES=$(generate_ip_rules)

    awk -v rules="$IP_RULES" '{
        if ($0 ~ /CF_IP_RULES_PLACEHOLDER/) {
            print rules
        } else {
            print
        }
    }' "$CONF_TEMPLATE" > "$CONF_FILE"

    echo "[entrypoint] 配置已生成"
}

# ============================================
# 函数: 清理旧轮转日志 + SQLite 维护
# ============================================
cleanup_logs() {
    # SmartDNS 自带轮转: audit-num=4 (4M×4=16MB), log-num=3 (4M×3=12MB)
    # 轮转后旧日志变成 .gz/.1/.2 等文件，SmartDNS 不会删除，手动清理

    # 删除超过 7 天的轮转日志
    if [ -d "$LOG_DIR" ]; then
        deleted=$(find "$LOG_DIR" \( -name "*.gz" -o -name "*.log.[0-9]*" -o -name "*.[0-9]" \) -mtime +7 -delete -print 2>/dev/null | wc -l)
        [ "$deleted" -gt 0 ] && echo "[cron] 清理了 ${deleted} 个旧日志文件"
    fi

    # SQLite 碎片整理: 当数据库文件 > 500MB 时执行 VACUUM
    # 跳过正在使用的数据库 (检查 WAL 文件大小, > 0 说明有活跃事务)
    if [ -f "$DB_FILE" ]; then
        db_size=$(stat -c%s "$DB_FILE" 2>/dev/null || echo 0)
        if [ "$db_size" -gt 524288000 ]; then
            wal_file="${DB_FILE}-wal"
            wal_size=$(stat -c%s "$wal_file" 2>/dev/null || echo 0)
            if [ "$wal_size" -lt 1048576 ]; then
                echo "[cron] DB 碎片整理 (${db_size} bytes)..."
                sqlite3 "$DB_FILE" "VACUUM;" 2>/dev/null && echo "[cron] VACUUM 完成" || echo "[cron] VACUUM 失败"
            else
                echo "[cron] WAL 活跃 (${wal_size} bytes)，跳过 VACUUM"
            fi
        fi
    fi
}

# ============================================
# 函数: 后台定期刷新 (每 6 小时)
# ============================================
periodic_refresh() {
    while true; do
        sleep 21600
        echo "[cron] --- 定期刷新开始 ---"
        download_cf_ips
        generate_config
        cleanup_logs
        echo "[cron] --- 定期刷新完成 (下次 6 小时后) ---"
    done &
}

# ============================================
# 执行
# ============================================

mkdir -p "$CF_DIR"

# 首次: 下载 CF IP 段 + 清理旧日志 + 生成配置
download_cf_ips
cleanup_logs

# 初始化优选 IP 文件 (仅首次)
[ -f "${CF_DIR}/preferred-ipv4.txt" ] || printf "# Cloudflare 优选 IPv4 (每行一个 IP)\n# 修改后重启容器生效\n154.17.3.148\n154.17.225.54\n" > "${CF_DIR}/preferred-ipv4.txt"
[ -f "${CF_DIR}/preferred-ipv6.txt" ] || printf "# Cloudflare 优选 IPv6 (每行一个 IP)\n# 当前策略: 仅返回 IPv4，此文件暂不使用\n# 2606:4700::1111\n" > "${CF_DIR}/preferred-ipv6.txt"

generate_config
periodic_refresh

echo "[entrypoint] 启动 SmartDNS..."
exec smartdns -f -c "$CONF_FILE"
