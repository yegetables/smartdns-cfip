# CF IP 优选项目（CFData-WEB）

## 项目目录

```
D:\tools\cf-data-web\
├── cfdata-windows-amd64.exe    # 主程序（CLI）
├── cfdata-config.json          # 配置文件（自动生成）
├── GeoLite2-ASN.mmdb           # 地理数据库
├── locations.json              # 数据中心位置
├── ports\                      # 输入 IP 列表
│   ├── 443\ALL.txt             # 标准 HTTPS 端口
│   ├── 8443\ALL.txt            # 非标端口
│   └── ...
├── scripts\                    # Python 脚本
│   ├── cfrunner.py             # 两条流程共用的库模块（非可执行脚本）
│   ├── cf-optimize.py          # 流程1（源流程）：ports/PORT/ALL.txt 测速
│   ├── bestcf-download.py      # 流程2：按 download-list.txt 用 aria2c 下载聚合源
│   ├── bestcf-merge.py         # 流程2：合并 raw/ 下载文件 → merged-raw.txt
│   ├── bestcf-optimize.py      # 流程2（现流程）：merged-raw.txt 测速
│   ├── deploy-cf.py            # 部署到 pve.fnos
│   ├── sort-results.py         # 终端查看 ip.csv 排序
│   └── to-preferred-ip-list.py # ip.txt → 纯 IP 列表（手动工具）
└── outputs\                    # 测速输出（流程1、流程2共享，互相覆盖）
    ├── cf-optimize.log         # 流程1运行日志 (tail -f)
    ├── port-443.csv            # 流程1测速原始数据
    ├── port-443-ip.txt         # 流程1测速达标结果
    ├── edgetunnel.txt          # 合并结果 (top N，流程1/2 共享，谁后跑覆盖谁)
    ├── ip.txt                  # 同 edgetunnel 格式（流程1/2 共享）
    ├── preferred-ipv4.txt      # 纯 IP 列表（仅443端口，流程1/2 共享）
    └── bestcf-tmp\             # 流程2专属中间目录
        ├── download-list.txt   # 待下载的聚合源 URL 列表
        ├── raw\                # 下载得到的原始文件
        ├── merged-raw.txt      # raw/ 合并结果（已排除"联通"/"电信"关键字行）
        ├── bestcf-ip.csv       # 流程2测速原始数据
        ├── bestcf-ip.txt       # 流程2测速达标结果
        └── bestcf-optimize.log # 流程2运行日志
```

## 首次使用

```bash
# 克隆后在项目根目录执行，自动下载适配架构的 cfdata 主程序
python scripts/setup.py
```

## 脚本用法

### cf-optimize.py — 流程1（源流程）

```bash
cd D:/tools/cf-data-web
python scripts/cf-optimize.py [端口号]
# 默认端口 443
```

**流程：**
1. 合并 上次 edgetunnel.txt + ports/PORT/ALL.txt 前 N 条 → 统一源文件
2. 一次统一测速（后台执行 + 20s 日志监控）
3. 排序去重取 top N → edgetunnel.txt
4. 生成 ip.txt + preferred-ipv4.txt（仅443端口）
5. 清理中间文件

**可调参数（文件顶部）：**
```python
SPEEDMIN = 3       # 速度达标下限 MB/s
SPEEDLIMIT = 10    # 最终保留数
SPEEDTEST = 8      # 测速并发线程数
RESULTLIMIT = 400  # 延迟扫描上限
```

### bestcf-optimize.py — 流程2（现流程，爬虫聚合源）

```bash
cd D:/tools/cf-data-web
# 1. 下载聚合源（支持 aria2c 断点续传）
python scripts/bestcf-download.py
# 2. 合并 raw/ 下载文件（排除含"联通"/"电信"关键字的行）
python scripts/bestcf-merge.py
# 3. 合并上次 edgetunnel.txt + merged-raw.txt 后统一测速
python scripts/bestcf-optimize.py [端口号]
# 默认端口 443
```

**流程：**
1. 合并 上次 edgetunnel.txt + outputs/bestcf-tmp/merged-raw.txt 前 N 条 → 统一源文件
2. 一次统一测速（后台执行 + 20s 日志监控）
3. 排序去重取 top N → edgetunnel.txt
4. 生成 ip.txt + preferred-ipv4.txt（仅443端口）
5. 清理中间文件

**可调参数（文件顶部）：**
```python
DELAY = 500          # 扫描合格延迟 ms
RESULTLIMIT = 10000  # 扫描合格数量上限
SPEEDMIN = 5         # 速度达标下限 MB/s
SPEEDLIMIT = 20      # 最终保留数
SPEEDTEST = 8        # 测速并发线程数
```

> 流程1、流程2的最终产出 `outputs/edgetunnel.txt`、`outputs/ip.txt`、`outputs/preferred-ipv4.txt` 是**同一份文件**，两条流程互相覆盖对方的结果（谁后运行谁生效）；测速原始数据/日志等中间文件仍按各自流程的前缀命名，不互相覆盖。

### deploy-cf.py — 部署到远程服务器

```bash
python scripts/deploy-cf.py
```

自动执行：
1. dos2unix 转换换行符
2. scp preferred-ipv4.txt → pve.fnos
3. scp edgetunnel.txt → pve.fnos
4. ssh git add + commit + push
5. ssh docker restart smartdns

空文件保护：两个源文件都为空时终止部署。

### 后处理

```bash
# 查看排序（只显示 > N MB/s）
python scripts/sort-results.py outputs/ip.csv 1

# 只看 IP
python scripts/sort-results.py outputs/ip.csv 1 --ip

# 提取纯 IP 列表
python scripts/to-preferred-ip-list.py outputs/edgetunnel.txt -o outputs/preferred-ipv4.txt
```

## cfdata CLI 主要参数

| 参数 | 说明 |
|------|------|
| `-cli` | CLI 模式 |
| `-mode=nsb` | 非标模式 |
| `-dns=223.5.5.5` | 指定 DNS |
| `-fields=ipport,loc,latency,speed` | 导出字段 |
| `-nsbfile=...` | 输入文件路径 |
| `-nsbfallbackport=443` | 缺省端口补全 |
| `-nsbqualified` | 只输出达标结果 |
| `-nsbspeedmin=3` | 速度下限 MB/s |
| `-nsbspeedlimit=10` | 达标结果上限 |
| `-nsbspeedtest=8` | 测速并发数 |
| `-nsbresultlimit=400` | 扫描上限 |
| `-nocolor` | 禁用 ANSI 颜色 |

> `-out` 参数可能报错，统一用默认名 ip.csv/ip.txt 然后 mv 改名。

## 重要约定和陷阱

### 换行符 — 所有文件优先 LF

所有生成的文件优先使用 Unix 换行符（LF, `\n`）。处理优先级：
1. 优先检查 `dos2unix` 命令是否存在，有则直接转换
2. 无则手动替换：`sed -i 's/\r$//' 文件` 或 `tr -d '\r' < 文件 > 新文件`

Python 写入时用 `newline="\n"`，部署前还有 dos2unix 双重保险。

### BOM 字符

cfdata 输出的 txt 以 UTF-8 BOM（`\ufeff`）开头。读取后需 `line.strip().strip('\ufeff')` 去除。

### 后台执行 + 日志监控（防超时丢数据）

cfdata 仅在测速完全结束后才一次性写入输出文件。前台等待如果超时会导致所有数据丢失。脚本采用：
- cfdata 在后台运行，stdout/stderr 追加到 `outputs/cf-optimize.log`
- 每 20 秒用 `tail -n 10` 读取日志最后 10 行对比
- 连续 20 秒无新输出则提示用户
- 进程退出后自动 mv 结果文件

### 代理环境下测速可能失败

代理/VPN 下速度测试可能全部报错（"未发现有效 IP"），但 IP 实际存活。先用 `-nsbspeedtest=0` 纯延迟扫描确认。

### `-nsbqualified` 配合注意

设 `-nsbqualified=true` 且所有速度测试失败时工具无输出。设 `-nsbqualified=false`（默认值）可输出含 `--` 的延迟结果。

## 远程服务器信息

- 主机：pve.fnos
- 仓库：`/home/ajian/compose-all/1panel-compose/smartdns-cfip`
- 目标路径：`cloudflare-ips/preferred-ipv4.txt`、`others-preferred-cfip/edgetunnel.txt`
- 部署后：docker restart smartdns
- 远程默认 shell 为 fish，ssh 命令注意语法兼容

## 工作流记忆

- 每次测速先读取 outputs/edgetunnel.txt 作为旧 IP 源（流程1、流程2共用同一份 edgetunnel.txt）
- 合并旧 IP + 本流程新数据源（流程1: ALL.txt；流程2: merged-raw.txt）统一测速
- 排序去重取 top N
- preferred-ipv4.txt 生成时仅保留443端口的条目（edgetunnel.txt 本身不做端口过滤）
- 部署前 dos2unix 转 LF
- 项目经验已全部位于本项目 CLAUDE.md，不再写入 agent 全局记忆
