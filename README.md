# SmartDNS + Cloudflare 优选 IP

SmartDNS Docker 部署，自动 Cloudflare IP 段更新 + 优选 IPv4 替换 + 日志自动清理。

## 功能

- **Cloudflare 优选 IP**：匹配到 CF IP 的域名，A 记录替换为优选 IPv4，AAAA 记录直接屏蔽
- **自动更新 CF IP 段**：每天从 `cloudflare.com/ips-v4|v6` 拉取最新 CIDR
- **日志清理**：每天清理 7 天前的轮转日志 `.gz`；SQLite 超 500MB 自动 VACUUM
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
│   ├── preferred-ipv4.txt     # 优选 IPv4 地址 ← CFData-WEB 产出
│   └── preferred-ipv6.txt     # 优选 IPv6 (当前未使用)
├── scripts/                   # CFData-WEB 优选工具（见下文）
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

---

# CFData-WEB — CF IP 优选工具

Cloudflare IP 优选工具。从多个聚合源拉取 CF IP，测速后筛选最优节点，自动部署到 smartdns。

## 快速开始

```bash
# 1. 克隆后安装（自动下载 cfdata 主程序）
python scripts/setup.py

# 2. 拉取聚合源 → 合并 → 测速（推荐流程）
python scripts/bestcf-download.py         # 从 47+ 个聚合源下载 IP
python scripts/bestcf-merge.py            # 合并 raw/ 下载文件
python scripts/bestcf-optimize.py         # 测速，输出 top 20 节点

# 3. 部署到远程服务器
python scripts/deploy-cf.py
```

## 环境要求

- Python 3.8+
- [aria2c](https://aria2.github.io/)（下载聚合源用，`scoop install aria2` 或 `apt install aria2`）
- `dos2unix`（可选，部署时会自动调用）
- Windows / Linux / macOS 均可

## 双流程说明

| | 流程1（cf-optimize.py） | 流程2（bestcf-*，默认推荐） |
|---|---|---|
| 输入源 | `ports/443/ALL.txt`（本地维护的 IP 列表） | 47+ 个线上聚合源（自动拉取） |
| 数据量 | 几百条 | 几千条 |
| 速度下限 | 3 MB/s | 5 MB/s |
| 保留数 | 10 个 | 20 个 |
| 适用场景 | 快速验证、小范围测速 | 日常优选 |

> 两条流程共用 `outputs/edgetunnel.txt`、`outputs/ip.txt`、`outputs/preferred-ipv4.txt`，谁后运行谁覆盖。

## 完整用法

### 下载聚合源

```bash
python scripts/bestcf-download.py
```

- 通过 aria2c 断点续传，重复运行跳过已有文件
- 原始失败 = auto_retry via gh-proxy.com
- 运行结束输出汇总：成功/失败数量和列表

### 合并下载文件

```bash
python scripts/bestcf-merge.py
```

- 合并 `outputs/bestcf-tmp/raw/` 下所有文件
- 自动排除含"联通"/"电信"的行

### 测速

```bash
# 推荐（不合并旧 IP）
python scripts/bestcf-optimize.py

# 指定端口
python scripts/bestcf-optimize.py --port 8443

# 合并上次结果
python scripts/bestcf-optimize.py --merge

# 向后兼容写法
python scripts/bestcf-optimize.py 443 --no-merge
```

可调参数（文件顶部）：

```python
DELAY = 500          # 扫描合格延迟 ms
RESULTLIMIT = 10000  # 扫描合格数量上限
SPEEDMIN = 5         # 速度达标下限 MB/s
SPEEDLIMIT = 20      # 最终保留数
SPEEDTEST = 8        # 测速并发线程数
```

### 流程1（本地列表测速）

```bash
python scripts/cf-optimize.py [端口] [--no-merge]
```

```python
SPEEDMIN = 3         # 速度达标下限 MB/s
SPEEDLIMIT = 10      # 最终保留数
SPEEDTEST = 8        # 测速并发线程数
RESULTLIMIT = 400    # 扫描上限
```

### 部署到远程服务器

```bash
python scripts/deploy-cf.py
```

自动执行：
1. dos2unix 转 LF
2. scp 上传到 pve.fnos
3. git add + commit + push（被拒时自动 rebase 重试）
4. docker restart smartdns

### 后处理工具

```bash
# 查看测速结果排序
python scripts/sort-results.py outputs/ip.csv 1

# 只看 IP
python scripts/sort-results.py outputs/ip.csv 1 --ip

# 提取纯 IP 列表
python scripts/to-preferred-ip-list.py outputs/edgetunnel.txt -o outputs/preferred-ipv4.txt
```

## cfdata CLI 参数参考

| 参数 | 说明 |
|------|------|
| `-cli` | CLI 模式 |
| `-mode=nsb` | 非标模式 |
| `-dns=223.5.5.5` | 指定 DNS |
| `-fields=ipport,loc,latency,speed` | 导出字段 |
| `-nsbfile=<path>` | 输入文件路径 |
| `-nsbfallbackport=443` | 缺省端口补全 |
| `-nsbqualified` | 只输出达标结果 |
| `-nsbspeedmin=3` | 速度下限 MB/s |
| `-nsbspeedlimit=10` | 达标结果上限 |
| `-nsbspeedtest=8` | 测速并发数 |
| `-nsbresultlimit=400` | 扫描上限 |
| `-nocolor` | 禁用 ANSI 颜色 |

## 注意事项

### 换行符

所有生成文件优先使用 LF。Python 写入时 `newline="\n"`，部署前 dos2unix 双保险。

### BOM 字符

cfdata 输出文件以 UTF-8 BOM（`\ufeff`）开头。读取后需 `line.strip().strip('\ufeff')` 去除。

### 后台执行 + 日志监控

cfdata 仅测速结束时才写入结果文件。脚本在后台启动 cfdata，每 20s 检查日志变化，同时通过进程状态确认 cfdata 仍在运行。空闲超时后自动等待，不丢数据。

### 代理环境

代理/VPN 下测速可能全部失败（报"未发现有效 IP"），需要时可临时关闭代理，或用 `-nsbspeedtest=0` 纯延迟扫描。

### `-nsbqualified` 配合

设 `-nsbqualified=true` 且全不达标时输出为空。`false`（默认）可输出含 `--` 的延迟结果。

### 部署信息

- 远程主机：pve.fnos
- 仓库：`/home/ajian/compose-all/1panel-compose/smartdns-cfip`
- 目标：`cloudflare-ips/preferred-ipv4.txt` + `others-preferred-cfip/edgetunnel.txt`
- 远程 shell 为 fish，ssh 命令注意语法兼容

## 目录结构

```
├── cfdata-windows-amd64.exe    # cfdata CLI 主程序
├── cfdata-config.json          # 自动生成的配置
├── GeoLite2-ASN.mmdb           # IP 地理数据库
├── locations.json              # 数据中心位置
├── ports/                      # 本地 IP 列表（流程1 输入）
│   ├── 443/ALL.txt
│   └── 8443/ALL.txt
├── scripts/
│   ├── cfrunner.py             # 共用库模块
│   ├── cf-optimize.py          # 流程1
│   ├── bestcf-download.py      # 流程2 下载
│   ├── bestcf-merge.py         # 流程2 合并
│   ├── bestcf-optimize.py      # 流程2 测速
│   ├── deploy-cf.py            # 部署
│   ├── sort-results.py         # 排序查看
│   └── to-preferred-ip-list.py # 纯 IP 提取
└── outputs/
    ├── edgetunnel.txt           # 合并结果
    ├── ip.txt                   # 同 edgetunnel 格式
    ├── preferred-ipv4.txt       # 纯 IP 列表
    └── bestcf-tmp/              # 流程2 中间文件
