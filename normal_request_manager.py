import atexit
import json
import os
import random
import sys
import threading
import time
import traceback
from collections import defaultdict
from threading import Lock, Semaphore, Thread

from query_and_preserve import query_and_preserve
from query_and_collect_ticket import query_and_collect_ticket
from query_and_enter_station import query_and_enter_station
from query_and_cancel import query_one_and_cancel

from atomic_queries import (
    _login,
    _query_orders,
    _query_high_speed_ticket,
    _pay_one_order,
    _collect_one_order,
    _enter_station,
    bind_thread_user,
)
from traffic_log import clear_traffic_context, set_traffic_context, tlog
from traffic_stats import STATS
from config import DEPARTURE_DATE, HTTP_TIMEOUT
from seed_od import SEED_HIGH_SPEED_PLACE_PAIRS, first_non_empty_trips

from utils import random_boolean, random_form_list

_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_ACCOUNTS_FILE = os.path.join(_DIR, "uestc_loadtest_accounts.json")

# 同时最多 N 条线程在执行「单次业务迭代」
LOAD_THREADS = max(1, int(os.environ.get("LOAD_THREADS", "5")))
# 累计执行多少次「一轮 preserve + 订单后续」（默认与旧版「LOAD_THREADS 条线程 × 30 次」相当）
_TRAFFIC_DEFAULT_INNER = str(LOAD_THREADS * 30)
TRAFFIC_INNER_ITERATIONS = max(1, int(os.environ.get("TRAFFIC_INNER_ITERATIONS", _TRAFFIC_DEFAULT_INNER)))
# 按运行时长停止（秒）；>0 时忽略 TRAFFIC_INNER_ITERATIONS
TRAFFIC_DURATION_SECONDS = max(0, int(float(os.environ.get("TRAFFIC_DURATION_SECONDS", "0"))))


def load_loadtest_accounts():
    """Load [{username, password, userId?}, ...] from JSON (see register_uestc_loadtest_accounts.py)."""
    path = os.environ.get("TRAIN_TICKET_ACCOUNTS_FILE", _DEFAULT_ACCOUNTS_FILE)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"未找到账号文件: {path}\n请先执行: python register_uestc_loadtest_accounts.py"
        )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list) or not data:
        raise ValueError(f"账号文件无效或为空: {path}")
    for row in data:
        if not isinstance(row, dict) or not row.get("username") or not row.get("password"):
            raise ValueError(f"账号行缺少 username/password: {row}")
    return data


def _get_headers_store():
    return defaultdict(lambda: {"Content-Type": "application/json"})


def _register_stats_dump() -> None:
    """进程退出（含 Ctrl-C）时兜底写出统计 JSON，避免中断丢数据。"""
    path = os.environ.get("TRAFFIC_STATS_JSON")
    if not path:
        return

    def _dump() -> None:
        STATS.finish()
        try:
            STATS.dump_json(path)
        except Exception:
            pass

    atexit.register(_dump)


def _fetch_unpaid_pairs(headers):
    """查询未支付订单池（普通 + 普铁/其他）。

    返回 (pairs, ok)：ok=False 表示至少一侧查询失败，不能用于新单 diff。
    """
    normal = _query_orders(headers=headers, types=tuple([0]))
    other = _query_orders(headers=headers, types=tuple([0]), query_other=True)
    ok = normal is not None and other is not None
    return (normal or []) + (other or []), ok


def run_one_traffic_iteration(
    account: dict, headers: dict, per_account_idx: int, worker_id: int = 0
) -> None:
    """单次业务：刷新登录（每 20 次）、订票，然后在同一张新订单上完成 支付→取票→进站（或取消）。"""
    un = account["username"]
    pw = account["password"]

    now_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    set_traffic_context(worker_id, un, per_account_idx)
    try:
        tlog(f"══ iteration begin time={now_time}")

        if per_account_idx % 20 == 0 or not headers.get("Authorization"):
            uid, token = _login(username=un, password=pw)
            if uid is not None and token is not None:
                headers["Authorization"] = "Bearer " + token
                account["userId"] = uid
                tlog("auth refreshed (scheduled or missing header)", 1)
            else:
                tlog("login failed, skip iteration", 1)
                return

        uid_tls = account.get("userId")
        if not uid_tls:
            uid, token = _login(username=un, password=pw)
            if uid is None or token is None:
                tlog("login failed (no userId in account file), skip", 1)
                return
            headers["Authorization"] = "Bearer " + token
            account["userId"] = uid
            uid_tls = uid

        bind_thread_user(uid_tls)

        tlog("step snapshot unpaid pool", 1)
        before_pairs, before_ok = _fetch_unpaid_pairs(headers)
        tlog(f"unpaid pool before={len(before_pairs)} ok={before_ok}", 1)

        tlog("step preserve", 1)
        res = query_and_preserve(headers)
        if res.get("error"):
            tlog(f"preserve.ERROR {res['error']}", 1)
            return

        target_pairs = []
        if res.get("order_created"):
            after_pairs, after_ok = _fetch_unpaid_pairs(headers)
            if before_ok and after_ok:
                before_ids = {p[0] for p in before_pairs}
                target_pairs = [p for p in after_pairs if p[0] not in before_ids]
                if len(target_pairs) > 1:
                    tlog(f"new-order diff got {len(target_pairs)} candidates, pick one", 1)
            if not target_pairs:
                tlog("new-order diff unavailable, fallback to unpaid pool", 1)
                target_pairs = after_pairs or before_pairs
        else:
            tlog("preserve did not create order, fallback to unpaid pool", 1)
            after_pairs, _ = _fetch_unpaid_pairs(headers)
            target_pairs = after_pairs or before_pairs

        target = random_form_list(target_pairs) if target_pairs else None
        if target:
            tlog(f"chain target order_id={target[0]} trip_id={target[1]}", 1)

        if random_boolean() and random_boolean():
            tlog("branch cancel random", 1)
            query_one_and_cancel(headers, pairs=([target] if target else None))
            STATS.record("chain", "skip", detail="cancel_branch")
        else:
            tlog("branch pay → collect → enter_station", 1)
            paid_id = None
            if target:
                paid_id = _pay_one_order(target[0], target[1], headers=headers)
            if paid_id:
                collected_id = _collect_one_order(order_id=paid_id, headers=headers)
                if collected_id:
                    entered_id = _enter_station(order_id=collected_id, headers=headers)
                    if entered_id:
                        STATS.record("chain", "success", detail=f"order_id={paid_id}")
                    else:
                        STATS.record("chain", "partial", detail=f"enter_station_fail order_id={paid_id}")
                        query_and_enter_station(headers)
                else:
                    STATS.record("chain", "partial", detail=f"collect_fail order_id={paid_id}")
                    query_and_collect_ticket(headers)
                    query_and_enter_station(headers)
            else:
                STATS.record(
                    "chain",
                    "business_fail" if target else "skip",
                    detail="pay_fail" if target else "no_target",
                )
                query_and_collect_ticket(headers)
                query_and_enter_station(headers)

        tlog("══ iteration end", 1)
    finally:
        clear_traffic_context()


def main_thread():
    accounts = load_loadtest_accounts()
    n_acc = len(accounts)
    _register_stats_dump()

    start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(
        "\n".join(
            [
                "========== train-ticket traffic ==========",
                f"start: {start_time}",
                f"departure date: {DEPARTURE_DATE}",
                f"LOAD_THREADS={LOAD_THREADS} TRAFFIC_INNER_ITERATIONS={TRAFFIC_INNER_ITERATIONS} accounts={n_acc}",
                f"accounts file: {os.environ.get('TRAIN_TICKET_ACCOUNTS_FILE', _DEFAULT_ACCOUNTS_FILE)}",
                f"consign={os.environ.get('TRAFFIC_ENABLE_CONSIGN', '0')} http_timeout={HTTP_TIMEOUT}s",
                (
                    f"duration={TRAFFIC_DURATION_SECONDS}s（>0 时忽略轮数，到点自动停止）"
                    if TRAFFIC_DURATION_SECONDS > 0
                    else "duration=0（按轮数运行）"
                ),
                "log format: [W<槽位> tid=<OS线程号> user=<账号> idx=<该账号第几次迭代>]",
                "并发: 全局最多 LOAD_THREADS 条线程；同 username 互斥串行；"
                "每轮迭代后 sleep 0~5s；启动各工作线程前 sleep 0~5s。",
                "==========================================\n",
            ]
        )
    )

    sem = Semaphore(LOAD_THREADS)
    inner_lock = Lock()
    inner_done = {"n": 0}
    deadline_holder = {"at": None}
    acc_locks = {a["username"]: Lock() for a in accounts}
    acc_iter = defaultdict(int)
    rr = {"i": 0}
    rr_lock = Lock()
    headers_store = _get_headers_store()

    def pick_account():
        with rr_lock:
            k = rr["i"] % n_acc
            rr["i"] += 1
        return accounts[k]

    def make_pool_worker(worker_id: int):
        def pool_worker():
            threading.current_thread().name = f"traffic-W{worker_id}"
            while True:
                if TRAFFIC_DURATION_SECONDS > 0:
                    dl = deadline_holder["at"]
                    if dl is not None and time.monotonic() >= dl:
                        return
                else:
                    with inner_lock:
                        if inner_done["n"] >= TRAFFIC_INNER_ITERATIONS:
                            return
                        inner_done["n"] += 1

                acc = pick_account()
                un = acc["username"]
                # 先占账号锁：同一 user 串行；避免在等该锁时还占着全局 sem 槽位
                with acc_locks[un]:
                    sem.acquire()
                    try:
                        i = acc_iter[un]
                        acc_iter[un] = i + 1
                        hdr = headers_store[un]
                        run_one_traffic_iteration(acc, hdr, i, worker_id)
                    except Exception as e:
                        STATS.record("iteration", "exception", detail=f"{type(e).__name__}: {e}")
                        tlog(f"iteration EXCEPTION {type(e).__name__}: {e}", 1)
                        traceback.print_exc()
                    finally:
                        sem.release()

                time.sleep(random.uniform(0.0, 5.0))

        return pool_worker

    threads = []
    for wi in range(LOAD_THREADS):
        time.sleep(random.uniform(0.0, 5.0))
        t = Thread(target=make_pool_worker(wi), daemon=False)
        t.start()
        threads.append(t)

    if TRAFFIC_DURATION_SECONDS > 0:
        deadline_holder["at"] = time.monotonic() + TRAFFIC_DURATION_SECONDS

    for t in threads:
        t.join()

    end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    STATS.finish()
    print(f"\n========== traffic finished start={start_time} end={end_time} ==========\n")
    print(STATS.render_summary())
    stats_path = os.environ.get("TRAFFIC_STATS_JSON")
    if stats_path:
        STATS.dump_json(stats_path)
        print(f"stats json: {stats_path}")


def query_order():
    accounts = load_loadtest_accounts()
    a = accounts[0]
    headers = {"Content-Type": "application/json"}
    uid, token = _login(username=a["username"], password=a["password"])
    if uid is not None and token is not None:
        headers["Authorization"] = "Bearer " + token
    else:
        raise SystemExit("login failed")

    start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"start:{start_time}")

    for i in range(50):
        pairs = _query_orders(headers=headers, types=tuple([0, 1]), query_other=False)
        print(pairs)

    end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"start:{start_time} end:{end_time}")


def query_tickets():
    accounts = load_loadtest_accounts()
    a = accounts[0]
    headers = {"Content-Type": "application/json"}
    uid, token = _login(username=a["username"], password=a["password"])
    if uid is not None and token is not None:
        headers["Authorization"] = "Bearer " + token
    else:
        raise SystemExit("login failed")

    date = DEPARTURE_DATE

    start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"start:{start_time}")

    for i in range(50):
        pair, trip_ids = first_non_empty_trips(
            _query_high_speed_ticket, SEED_HIGH_SPEED_PLACE_PAIRS, headers, date)
        print(pair, trip_ids)

    end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"start:{start_time} end:{end_time}")


if __name__ == '__main__':
    try:
        main_thread()
    except (FileNotFoundError, ValueError) as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1) from e
