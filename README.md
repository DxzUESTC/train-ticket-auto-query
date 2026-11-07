# train-ticket-auto-query

Train Ticket Auto Query Python Scripts

## Environment

| Variable | Meaning |
|----------|---------|
| `TRAIN_TICKET_BASE` | Gateway root URL (default `http://192.168.100.11:30467`) |
| `TRAIN_TICKET_DATE` | `today`, `tomorrow`, or `YYYY-MM-DD` (default `today`; must satisfy backend `afterToday` in travel services) |
| `TRAIN_TICKET_ACCOUNTS_FILE` | Account list JSON used by `normal_request_manager` / `locustfile` / `seed_contacts`; default `uestc_loadtest_accounts.json` |

## Seed routes (aligned with upstream `train-ticket`)

Simulated traffic uses **only** origin–destination pairs that exist in upstream seed data (`seed_od.py`):

- **High speed** (`/api/v1/travelservice/trips/left`): from `ts-travel-service/.../travel/init/InitData.java` — e.g. **Shang Hai ↔ Su Zhou** (G/D trips first segment).
- **Normal** (`/api/v1/travel2service/trips/left`): from `ts-travel2-service/.../travel2/init/InitData.java` — e.g. **Shang Hai ↔ Nan Jing** (Z/T/K trips first segment).

There is no seed data for arbitrary cities (e.g. Haikou); empty trip lists for other OD are expected.

## How to use

```python
import logging
from queries import Query
from scenarios import query_and_preserve

# login train-ticket and store the cookies
q = Query(url)
if not q.login():
    logging.fatal('login failed')

# execute scenario on current user
query_and_preserve(q)

# or execute query directly
q.query_high_speed_ticket()
```

## 压测账号准备（批量建号）

压测账号由脚本走网关的注册接口批量创建（不是直接写数据库），推荐顺序：

```bash
py -3.14 register_uestc_loadtest_accounts.py   # 1. 建号并写出 uestc_loadtest_accounts.json
py -3.14 seed_contacts_uestc_loadtest.py       # 2. 每个账号建一条默认联系人（幂等，preserve 必需）
./run.sh smoke                                 # 3. 接线检查，之后即可 warmup/baseline
```

`register_uestc_loadtest_accounts.py` 主要参数：

| 参数 | 默认 | 含义 |
|------|------|------|
| `--count` / `--start` | 10 / 1 | 账号数量与编号起点 |
| `--prefix` / `--password` | `uestc-test` / `111111` | 用户名前缀、统一密码 |
| `--out` | `uestc_loadtest_accounts.json` | 输出文件（缺省读 `TRAIN_TICKET_ACCOUNTS_FILE`） |
| `--base` | `TRAIN_TICKET_BASE` | 网关地址 |
| `--timeout` / `--retries` / `--backoff` | 60s / 3 / 2s | 单请求超时、最大尝试次数、退避基数 |
| `--dry-run` / `--skip-preflight` | - | 只打印计划 / 跳过网关可达性探测 |

行为约定：

- **幂等**：已存在的账号不会被修改，脚本改用登录回填 `userId`，可反复执行。
- **增量落盘**：每个账号成功即原子覆写输出文件（临时文件 + 替换），Ctrl-C 或个别失败不丢已完成部分。
- **重试**：只对传输错误和 5xx 做指数退避重试；4xx、密码错误等确定性失败立即返回，不拖慢。
- **退出码**：`0` 全部成功；`1` 有账号未解析（其余已落盘）；`2` 参数错误；`3` 网关不可达；`130` 被中断。
- 默认输出会覆盖仓库里的模板文件；不想产生 diff 可加 `--out uestc_loadtest_accounts.local.json`（已 gitignore）。
- 需要实验室内网可达（默认 `http://192.168.100.11:30467`）；连不上时脚本直接以退出码 3 失败，不会逐个账号空等超时。
- Windows 下用 `py -3.14` 运行（系统 `python` 3.11 未安装 `requests`）。

## 流量实验流程（预热 + 正式）

集群各服务长时间空闲后首次被调用会经历冷启动（单次可达 10-30s），因此每次实验必须**先预热、后正式**，否则冷启动延迟会污染数据。统一入口：

```bash
chmod +x run.sh          # 首次使用
./run.sh smoke           # 可选：1 线程 3 轮连通性检查
./run.sh warmup          # 预热：1 线程 20 轮，超时 120s
./run.sh baseline        # 正式基线：5 线程 1200 轮，超时 15s
./run.sh all             # 预热校验通过后自动接正式基线
```

- 产物在 `runs/`：`<时间戳>-<模式>-stats.json` 与同名 `.log`。
- 按时长跑（适合每天固定实验窗口）：`./run.sh baseline 1800` 表示跑 30 分钟，到点自动停止并输出汇总；也可用 `BASE_DURATION=1800 ./run.sh baseline`。时长模式下忽略轮数。
- `warmup` 结束会校验统计中 `exception`/`http_fail`，非零则中止；`all` 模式不会继续正式跑。
- 预热会覆盖 preserve/preserveOther/pay/collect/enter/cancel 等分支（随机 20 轮，约 1-3 分钟）。
- 跨午夜会因 travel 服务 `afterToday` 校验导致查票全空，长跑请避开 0 点或跨天后重启进程。
- 托运默认开启（约一半订票随机携带托运，覆盖 consign/consign-price 两个服务）；`TRAFFIC_ENABLE_CONSIGN=0 ./run.sh baseline` 可关闭。
- 常用覆盖变量：`WARM_ITERS`、`WARM_TIMEOUT`、`BASE_THREADS`、`BASE_ITERS`、`BASE_TIMEOUT`、`TRAFFIC_ENABLE_CONSIGN`、`TRAIN_TICKET_BASE`。
- 统计 JSON 在进程退出（含 Ctrl-C）时也会兜底落盘，中断不丢数据。

