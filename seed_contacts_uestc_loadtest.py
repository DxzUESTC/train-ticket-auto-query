#!/usr/bin/env python3
"""
为 uestc_loadtest_accounts.json 中每个账号登录后创建一条默认联系人（幂等：已存在则跳过）。

依赖：已执行 register_uestc_loadtest_accounts.py（或账号可登录），网关 TRAIN_TICKET_BASE 与 config 一致。

接口：POST {BASE}/api/v1/contactservice/contacts
权限：需该用户 JWT（ROLE_USER），见 ts-contacts-service SecurityConfig。

用法:
  python seed_contacts_uestc_loadtest.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Dict, List, Optional, Tuple

import requests

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from atomic_queries import _login  # noqa: E402
from config import BASE_URL  # noqa: E402

ACCOUNTS_FILE = os.path.join(_DIR, "uestc_loadtest_accounts.json")


def _load_accounts() -> List[Dict[str, Any]]:
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("accounts file must be a JSON list")
    return data


def create_contact(
    base: str,
    headers: Dict[str, str],
    user_id: str,
    username: str,
    phone_tail: str,
) -> Tuple[bool, str]:
    """POST one contact; return (ok, message)."""
    url = f"{base.rstrip('/')}/api/v1/contactservice/contacts"
    # 唯一索引 (account_id, document_number, document_type) — 用用户名区分证件号
    doc_num = f"LD{username.replace('-', '')}01"
    payload = {
        "accountId": user_id,
        "name": f"联系人_{username}",
        "documentType": 1,
        "documentNumber": doc_num,
        "phoneNumber": f"139{phone_tail}",
    }
    r = requests.post(
        url,
        json=payload,
        headers=headers,
        verify=False,
        timeout=60,
    )
    try:
        body = r.json()
    except ValueError:
        return False, r.text[:500]

    status = body.get("status")
    msg = str(body.get("msg", ""))
    if status == 1:
        return True, msg or "ok"
    if status == 0 and "exists" in msg.lower():
        return True, "skip exists"
    return False, str(body)


def main() -> int:
    base = BASE_URL
    rows = _load_accounts()
    ok_n = 0
    for i, row in enumerate(rows):
        un = row["username"]
        pw = row["password"]
        uid, token = _login(username=un, password=pw)
        if not uid or not token:
            print(f"[fail] login {un}")
            return 1
        hdr = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        phone_tail = f"{10000001 + i:08d}"
        good, msg = create_contact(base, hdr, uid, un, phone_tail)
        if good:
            print(f"[ok] {un} contact: {msg}")
            ok_n += 1
        else:
            print(f"[fail] {un} contact: {msg}")
            return 1

    print(f"Done. {ok_n}/{len(rows)} accounts have default contact.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
