import os

from query_and_preserve import query_and_preserve
from query_order_and_pay import query_order_and_pay
from query_and_collect_ticket import query_and_collect_ticket
from query_and_enter_station import query_and_enter_station
from query_and_cancel import query_one_and_cancel

from atomic_queries import _login, _query_orders, _query_high_speed_ticket
from config import DEPARTURE_DATE
from seed_od import SEED_HIGH_SPEED_PLACE_PAIRS, first_non_empty_trips

from utils import random_boolean
import time

from threading import Thread

# Same account + preserve is heavy; many threads often see HTTP 500 from gateway/services.
LOAD_THREADS = max(1, int(os.environ.get("LOAD_THREADS", "5")))


def main():
    headers = {"Content-Type": "application/json"}

    for i in range(30):
        now_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        print(f"now_time:{now_time}")

        if i % 20 == 0:
            uid, token = _login()
            if uid is not None and token is not None:
                headers["Authorization"] = "Bearer " + token
            else:
                print("login failed, skipping iteration")
                continue

        print(f"idx:{i}")
        query_and_preserve(headers)

        pairs = _query_orders(headers=headers, types=tuple([0, 1]))
        pairs2 = _query_orders(headers=headers, types=tuple([0, 1]), query_other=True)
        unpaid = (pairs or []) + (pairs2 or [])

        # 1/4 几率取消
        if random_boolean() and random_boolean():
            query_one_and_cancel(headers)
        else:
            if unpaid:
                query_order_and_pay(headers, unpaid)
            query_and_collect_ticket(headers)
            query_and_enter_station(headers)


def main_thread():
    threads = []

    start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"start:{start_time}")
    print(f"departure date (TRAIN_TICKET_DATE / config): {DEPARTURE_DATE}")
    print(f"LOAD_THREADS={LOAD_THREADS} (export LOAD_THREADS=1 to reduce preserve 500s)")

    for i in range(LOAD_THREADS):
        t = Thread(name="thread" + str(i), target=main)
        time.sleep(1)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"start:{start_time} end:{end_time}")


def query_order():
    headers = {"Content-Type": "application/json"}
    uid, token = _login()
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
    headers = {"Content-Type": "application/json"}
    uid, token = _login()
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
    main_thread()
