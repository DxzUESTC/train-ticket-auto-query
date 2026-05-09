import json
import os
import sys
import time
from threading import Thread

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

# Same account + preserve is heavy; many threads often see HTTP 500 from gateway/services.
LOAD_THREADS = max(1, int(os.environ.get("LOAD_THREADS", "5")))


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


def make_main(account: dict):
    """Each worker thread logs in as one fixed account (thread-local userId in atomic_queries)."""

    def main():
        headers = {"Content-Type": "application/json"}
        un = account["username"]
        pw = account["password"]

        for i in range(30):
            now_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            print(f"now_time:{now_time} user={un}")

            if i % 20 == 0:
                uid, token = _login(username=un, password=pw)
                if uid is not None and token is not None:
                    headers["Authorization"] = "Bearer " + token
                else:
                    print(f"login failed user={un}, skipping iteration")
                    continue

            print(f"idx:{i} user={un}")
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

    return main


def main_thread():
    accounts = load_loadtest_accounts()

    threads = []

    start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"start:{start_time}")
    print(f"departure date (TRAIN_TICKET_DATE / config): {DEPARTURE_DATE}")
    print(
        f"LOAD_THREADS={LOAD_THREADS} accounts={len(accounts)} "
        f"(export LOAD_THREADS=1 to reduce preserve 500s)"
    )
    print(f"accounts file: {os.environ.get('TRAIN_TICKET_ACCOUNTS_FILE', _DEFAULT_ACCOUNTS_FILE)}")

    n_acc = len(accounts)
    if LOAD_THREADS > n_acc:
        print(
            f"WARN: LOAD_THREADS({LOAD_THREADS}) > 账号数({n_acc})，将有多条线程共用同一账号 "
            f"(i % {n_acc})。若要「一线程一账号且不重复」，请设 LOAD_THREADS<={n_acc}。"
        )
    else:
        print(
            f"线程与账号: 共 {LOAD_THREADS} 条线程，各绑定 accounts[0..{LOAD_THREADS - 1}]，"
            f"互不切换用户（日志里 user= 应每条线程固定一个）。"
        )

    for i in range(LOAD_THREADS):
        acc = accounts[i % len(accounts)]
        t = Thread(name="thread" + str(i), target=make_main(acc))
        time.sleep(1)
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
