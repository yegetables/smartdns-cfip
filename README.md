# SmartDNS + Cloudflare 优选 IP

SmartDNS Docker 部署，自动 Cloudflare IP 段更新 + 优选 IPv4 替换 + 日志自动清理。

## 功能

- **Cloudflare 优选 IP**：匹配到 CF IP 的域名，A 记录替换为优选 IPv4，AAAA 记录直接屏蔽
- **自动更新 CF IP 段**：每 6 小时从 `cloudflare.com/ips-v4|v6` 拉取最新 CIDR
- **日志清理**：每 6 小时清理 7 天前的轮转日志 `.gz`；SQLite 超 500MB 自动 VACUUM
- **上游 DNS**：阿里 H3 (QUIC) 优先 → 阿里/腾讯 DoH → UDP → 114 fallback
- **WebUI 仪表盘**：`http://<IP>:6080` (admin / password)

## 文件结构

```
├── docker-compose.yml
├── smartdns.conf              # 配置模板 (挂载为 .template)
├── entrypoint.sh              # 启动脚本: 生成配置 + 定时刷新 + 日志清理
├── cloudflare-ips/
│   ├── cloudflare-ipv4.txt    # CF IPv4 CIDR (自动更新)
│   ├── cloudflare-ipv6.txt    # CF IPv6 CIDR (自动更新)
│   ├── preferred-ipv4.txt     # 优选 IPv4 地址 ← 你需要改这个
│   └── preferred-ipv6.txt     # 优选 IPv6 (当前未使用)
└── README.md
```

运行时自动创建:
```
├── smartdns-data/             # 缓存 + SQLite (runtime)
├── smartdns-config/           # 生成的实际配置 (runtime)
└── smartdns-logs/             # 审计 + 运行日志 (runtime)
```

## 快速部署

```bash
# 1. 克隆
git clone https://github.com/yegetables/smartdns-cfip.git
cd smartdns-cfip

# 2. 编辑优选 IP (可选)
vim cloudflare-ips/preferred-ipv4.txt

# 3. 启动
docker-compose up -d

# 4. 验证
dig @127.0.0.1 -p 6053 www.google.com A
dig @127.0.0.1 -p 6053 www.google.com AAAA   # 应返回 NODATA

# 5. 仪表盘
# 浏览器访问 http://<IP>:36080
```

## 优选 IP 配置

编辑 `cloudflare-ips/preferred-ipv4.txt`，每行一个 IP：

```
154.17.3.148
154.17.225.54
64.186.246.93
```

重启生效：`docker-compose restart`

## CF 域名解析行为

| 查询类型 | 效果 |
|---------|------|
| A 记录 | 返回优选 IPv4 地址 |
| AAAA 记录 | 返回 NODATA (屏蔽) |

## DNS 上游优先级

```
1. 阿里 DNS (H3/QUIC)   ← 最低延迟
2. 阿里 DNS (DoH)
3. 阿里/腾讯 DNS (UDP)
4. 114.114.114.114        ← Bootstrap + Fallback
```

## 缓存

| 参数 | 值 |
|------|-----|
| `cache-size` | 32768 条 |
| `cache-persist` | yes (重启保留) |
| `serve-expired` | no |
| `rr-ttl-reply-max` | 86400s |

## 日志

| 类型 | 单文件 | 轮转数 | 上限 |
|------|--------|--------|------|
| 审计日志 | 4MB | 4 | ~16MB |
| 运行日志 | 4MB | 3 | ~12MB |

轮转后的旧文件 (`.gz`) 每 6 小时自动清理 (7 天前)。

## 网络

使用 `1panel-network` (external)，端口映射：

| 容器端口 | 宿主机端口 | 用途 |
|---------|-----------|------|
| 53/udp | 6053 | DNS |
| 53/tcp | 6053 | DNS |
| 6080 | 36080 | WebUI |
