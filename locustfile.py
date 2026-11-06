"""Locust load generator for Train Ticket.

Usage:
    export TRAIN_TICKET_BASE=http://192.168.100.11:30467
    locust -f locustfile.py --headless -u 5 -r 1 -t 30m

Notes:
    - Reuses the existing atomic_queries / query_and_preserve business logic.
    - One Locust user consumes one account from uestc_loadtest_accounts.json.
      Do not set -u larger than the number of accounts unless account sharing is acceptable.
    - Detailed step-level stats are printed at test stop and optionally written to
      TRAFFIC_STATS_JSON.
"""

import json
import os
import threading

from locust import User, between, events, task

import atomic_queries as aq
import query_and_preserve as qp
from atomic_queries import _login, _query_high_speed_ticket, _query_normal_ticket
from normal_request_manager import run_one_traffic_iteration
from traffic_stats import STATS
from utils import random_boolean

_DEFAULT_ACCOUNTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "uestc_loadtest_accounts.json",
)

_ACCOUNTS = None
_ACCOUNT_LOCK = threading.Lock()
_NEXT_ACCOUNT = 0


def _load_accounts():
    global _ACCOUNTS
    if _ACCOUNTS is not None:
        return _ACCOUNTS

    path = os.environ.get("TRAIN_TICKET_ACCOUNTS_FILE", _DEFAULT_ACCOUNTS)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list) or not data:
        raise ValueError(f"invalid accounts file: {path}")

    _ACCOUNTS = data
    return data


def _next_account():
    global _NEXT_ACCOUNT
    accounts = _load_accounts()

    with _ACCOUNT_LOCK:
        index = _NEXT_ACCOUNT % len(accounts)
        _NEXT_ACCOUNT += 1

    return index, dict(accounts[index])


class TTUser(User):
    wait_time = between(1, 3)

    def on_start(self):
        base = (self.environment.host or os.environ.get("TRAIN_TICKET_BASE") or "").rstrip("/")
        if base:
            aq.base_address = base
            qp.BASE_URL = base

        self.account_index, self.account = _next_account()
        self.headers = {"Content-Type": "application/json"}
        self.iterations = 0

        with self.environment.events.request.measure("TASK", "login"):
            uid, token = self._login()
            if not (uid and token):
                raise RuntimeError("login failed")

    def _login(self):
        uid, token = _login(
            username=self.account["username"],
            password=self.account["password"],
        )
        if uid and token:
            self.account["userId"] = uid
            self.headers["Authorization"] = "Bearer " + token
        return uid, token

    def _ensure_auth(self):
        if not self.headers.get("Authorization") or self.iterations % 20 == 0:
            self._login()

    @task(40)
    def query_only(self):
        with self.environment.events.request.measure("TASK", "query_only"):
            self._ensure_auth()
            if random_boolean():
                trips = _query_high_speed_ticket(headers=self.headers)
            else:
                trips = _query_normal_ticket(headers=self.headers)

            if trips is None:
                raise RuntimeError("ticket query failed")

        self.iterations += 1

    @task(60)
    def full_chain(self):
        with self.environment.events.request.measure("TASK", "full_chain"):
            self._ensure_auth()
            run_one_traffic_iteration(
                self.account,
                self.headers,
                self.iterations,
                worker_id=self.account_index,
            )

        self.iterations += 1


@events.test_start.add_listener
def _on_test_start(environment, **kwargs):
    print(f"TRAIN_TICKET_BASE={aq.base_address}")
    print(f"accounts file={os.environ.get('TRAIN_TICKET_ACCOUNTS_FILE', _DEFAULT_ACCOUNTS)}")


@events.test_stop.add_listener
def _on_test_stop(environment, **kwargs):
    STATS.finish()
    print("\n" + STATS.render_summary())

    path = os.environ.get("TRAFFIC_STATS_JSON")
    if path:
        STATS.dump_json(path)
        print(f"stats json: {path}")
