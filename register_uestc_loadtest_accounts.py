#!/usr/bin/env python3
"""
批量注册压测账号 uestc-test1 … uestc-test10（密码均为 111111），并写入 uestc_loadtest_accounts.json。

依赖网关可访问（环境变量 TRAIN_TICKET_BASE，与 config.py 一致）。
已存在用户时会尝试登录并仍写入账号行（便于重复执行幂等更新 userId）。

用法:
  python register_uestc_loadtest_accounts.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from config import BASE_URL  # noqa: E402


OUTPUT_FILE = os.path.join(_DIR, "uestc_loadtest_accounts.json")
PASSWORD = "111111"
USER_NAMES = [f"uestc-test{i}" for i in range(1, 11)]


def _json(resp: requests.Response) -> Optional[dict]:
    try:
        return resp.json()
    except ValueError:
        return None


def register_user(base: str, username: str, password: str) -> Tuple[int, Optional[dict]]:
    url = f"{base.rstrip('/')}/api/v1/userservice/users/register"
    payload = {
        "userName": username,
        "password": password,
        "gender": 1,
        "documentType": 1,
        "documentNum": f"U{username.replace('-', '')}",
        "email": f"{username}@uestc.test",
    }
    r = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json"},
        verify=False,
        timeout=60,
    )
    return r.status_code, _json(r)


def login_user(base: str, username: str, password: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (userId, token) using same flow as atomic_queries._login."""
    session = requests.Session()
    session.verify = False
    b = base.rstrip("/")
    session.get(f"{b}/api/v1/verifycode/generate")
    login_url = f"{b}/api/v1/users/login"
    hdr = {
        "Origin": login_url,
        "Referer": f"{b}/client_login.html",
        "Content-Type": "application/json",
    }
    r = session.post(
        login_url,
        headers=hdr,
        json={"username": username, "password": password, "verificationCode": "1234"},
        timeout=60,
    )
    if r.status_code != 200:
        return None, None
    j = _json(r)
    if not isinstance(j, dict):
        return None, None
    inner = j.get("data")
    if not isinstance(inner, dict):
        return None, None
    return inner.get("userId"), inner.get("token")


def extract_user_id_from_register(body: Optional[dict]) -> Optional[str]:
    if not body or not isinstance(body, dict):
        return None
    if body.get("status") != 1:
        return None
    data = body.get("data")
    if isinstance(data, dict):
        return data.get("userId")
    return None


def main() -> int:
    base = BASE_URL
    rows: List[Dict[str, Any]] = []

    for username in USER_NAMES:
        code, body = register_user(base, username, PASSWORD)
        uid = extract_user_id_from_register(body)
        if uid:
            print(f"[ok] register {username} userId={uid}")
        else:
            print(f"[info] register {username} http={code} msg={(body or {}).get('msg')} → try login")
            uid, _tok = login_user(base, username, PASSWORD)
            if uid:
                print(f"[ok] login {username} userId={uid}")
            else:
                print(f"[fail] cannot resolve userId for {username}")
                return 1

        rows.append({"username": username, "password": PASSWORD, "userId": uid})
        time.sleep(0.15)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote {len(rows)} accounts to {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
