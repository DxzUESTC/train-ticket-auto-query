# train-ticket-auto-query

Train Ticket Auto Query Python Scripts

## Environment

| Variable | Meaning |
|----------|---------|
| `TRAIN_TICKET_BASE` | Gateway root URL (default `http://192.168.100.11:30467`) |
| `TRAIN_TICKET_DATE` | `today`, `tomorrow`, or `YYYY-MM-DD` (default `today`; must satisfy backend `afterToday` in travel services) |

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
- `warmup` 结束会校验统计中 `exception`/`http_fail`，非零则中止；`all` 模式不会继续正式跑。
- 预热会覆盖 preserve/preserveOther/pay/collect/enter/cancel 等分支（随机 20 轮，约 1-3 分钟）。
- 跨午夜会因 travel 服务 `afterToday` 校验导致查票全空，长跑请避开 0 点或跨天后重启进程。
- 常用覆盖变量：`WARM_ITERS`、`WARM_TIMEOUT`、`BASE_THREADS`、`BASE_ITERS`、`BASE_TIMEOUT`、`TRAFFIC_ENABLE_CONSIGN`、`TRAIN_TICKET_BASE`。
- 统计 JSON 在进程退出（含 Ctrl-C）时也会兜底落盘，中断不丢数据。

