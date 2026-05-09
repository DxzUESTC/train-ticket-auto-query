import json
import os
import random
import sys
import threading
import time
from collections import defaultdict
from threading import Lock, Semaphore, Thread

from query_and_preserve import query_and_preserve
from query_order_and_pay import query_order_and_pay
from query_and_collect_ticket import query_and_collect_ticket
from query_and_enter_station import query_and_enter_station
from query_and_cancel import query_one_and_cancel

from atomic_queries import _login, _query_orders, _query_high_speed_ticket
from config import DEPARTURE_DATE
from seed_od import SEED_HIGH_SPEED_PLACE_PAIRS, first_non_empty_trips

from utils import random_boolean

_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_ACCOUNTS_FILE = os.path.join(_DIR, "uestc_loadtest_accounts.json")

# 同时最多 N 条线程在执行「单次业务迭代」
LOAD_THREADS = max(1, int(os.environ.get("LOAD_THREADS", "5")))
# 累计执行多少次「一轮 preserve + 订单后续」（默认与旧版「LOAD_THREADS 条线程 × 30 次」相当）
_TRAFFIC_DEFAULT_INNER = str(LOAD_THREADS * 30)
TRAFFIC_INNER_ITERATIONS = max(1, int(os.environ.get("TRAFFIC_INNER_ITERATIONS", _TRAFFIC_DEFAULT_INNER)))


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


def run_one_traffic_iteration(account: dict, headers: dict, per_account_idx: int) -> None:
    """单次业务：刷新登录（每 20 次）、订票、付/取/进站或取消。"""
    un = account["username"]
    pw = account["password"]

    now_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"now_time:{now_time} user={un}")

    if per_account_idx % 20 == 0:
        uid, token = _login(username=un, password=pw)
        if uid is not None and token is not None:
            headers["Authorization"] = "Bearer " + token
        else:
            print(f"login failed user={un}, skipping iteration")
            return

    print(f"idx:{per_account_idx} user={un}")
    query_and_preserve(headers)

    pairs = _query_orders(headers=headers, types=tuple([0, 1]))
    pairs2 = _query_orders(headers=headers, types=tuple([0, 1]), query_other=True)
    unpaid = (pairs or []) + (pairs2 or [])

    if random_boolean() and random_boolean():
        query_one_and_cancel(headers)
    else:
        if unpaid:
            query_order_and_pay(headers, unpaid)
        query_and_collect_ticket(headers)
        query_and_enter_station(headers)


def main_thread():
    accounts = load_loadtest_accounts()
    n_acc = len(accounts)

    start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"start:{start_time}")
    print(f"departure date (TRAIN_TICKET_DATE / config): {DEPARTURE_DATE}")
    print(
        f"LOAD_THREADS={LOAD_THREADS} TRAFFIC_INNER_ITERATIONS={TRAFFIC_INNER_ITERATIONS} "
        f"accounts={n_acc}"
    )
    print(f"accounts file: {os.environ.get('TRAIN_TICKET_ACCOUNTS_FILE', _DEFAULT_ACCOUNTS_FILE)}")
    print(
        "并发模型: 全局最多 LOAD_THREADS 条线程；同一 username 互斥串行；"
        "每完成一轮迭代后随机 sleep 0~5s；启动每条工作线程前随机 sleep 0~5s。"
    )

    sem = Semaphore(LOAD_THREADS)
    inner_lock = Lock()
    inner_done = {"n": 0}
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

    def pool_worker():
        while True:
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
                    run_one_traffic_iteration(acc, hdr, i)
                finally:
                    sem.release()

            time.sleep(random.uniform(0.0, 5.0))

    threads = []
    for _ in range(LOAD_THREADS):
        time.sleep(random.uniform(0.0, 5.0))
        t = Thread(target=pool_worker, daemon=False)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"start:{start_time} end:{end_time}")


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
