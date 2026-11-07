#!/usr/bin/env python3
"""批量注册 Train-Ticket 压测账号，并生成账号清单（username / password / userId）。

接口依据（与 ts-user-service、ts-auth-service 源码一致）：
  POST {BASE}/api/v1/userservice/users/register
       body: {userName, password, gender, documentType, documentNum, email}
       成功: HTTP 201 + {"status": 1, "msg": "REGISTER USER SUCCESS", "data": {...userId...}}
       重名: HTTP 201 + {"status": 0, "msg": "USER HAS ALREADY EXISTS"}（不会覆盖已有账号）
  同名时的兜底：先 GET /api/v1/verifycode/generate 拿 cookie，再
       POST {BASE}/api/v1/users/login {username, password, verificationCode}
       用登录返回的 userId 回填，保证脚本可重复执行。

设计要点：
  - 幂等：已存在的账号走登录兜底，不重复建号、不修改已有密码。
  - 增量落盘：每个账号解析成功立即原子写（临时文件 + os.replace），
    中途失败或 Ctrl-C 不会丢掉已完成的部分。
  - 自动重试：仅对「传输层错误」和「5xx」做指数退避重试；4xx 与业务失败不重试，
    避免把密码错误之类的确定性失败拖成慢失败。
  - 失败不中止：单个账号最终失败只记录并继续，跑完后按失败数决定退出码。
  - 网关预检：默认先探测网关可达性，内网没连上时立即退出（退出码 3），
    而不是让每个账号各等一轮超时。

用法：
  py -3.14 register_uestc_loadtest_accounts.py
  py -3.14 register_uestc_loadtest_accounts.py --count 20
  py -3.14 register_uestc_loadtest_accounts.py --out uestc_loadtest_accounts.local.json
  py -3.14 register_uestc_loadtest_accounts.py --dry-run

环境变量：
  TRAIN_TICKET_BASE            网关地址，默认取 config.BASE_URL
  TRAIN_TICKET_ACCOUNTS_FILE   输出文件默认值（与 seed_contacts / normal_request_manager 一致）
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from config import BASE_URL  # noqa: E402

LOGGER = logging.getLogger("register_accounts")

DEFAULT_OUTPUT = os.path.join(_DIR, "uestc_loadtest_accounts.json")
DEFAULT_PASSWORD = "111111"
DEFAULT_PREFIX = "uestc-test"
DEFAULT_COUNT = 10
DEFAULT_START = 1
DEFAULT_TIMEOUT = 60.0
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 2.0
PREFLIGHT_TIMEOUT = 10.0

# 注册资料：压测账号只需能登录，性别与证件类型取后端默认值即可。
GENDER = 1
DOCUMENT_TYPE = 1
# 与 atomic_queries._login 保持一致的固定验证码（依赖集群侧放行）。
VERIFICATION_CODE = "1234"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_GATEWAY_UNREACHABLE = 3  # 2 被 argparse 的参数错误占用，这里避开
EXIT_INTERRUPTED = 130


# --------------------------------------------------------------------------- #
# 参数与日志
# --------------------------------------------------------------------------- #
def build_usernames(prefix: str, count: int, start: int) -> List[str]:
    """按前缀 + 序号生成用户名列表，例如 uestc-test1 … uestc-test10。"""
    return [f"{prefix}{index}" for index in range(start, start + count)]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="批量注册 Train-Ticket 压测账号并写出账号清单。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="账号数量")
    parser.add_argument("--start", type=int, default=DEFAULT_START, help="账号编号起点")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="用户名前缀")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="统一密码")
    parser.add_argument(
        "--out",
        default=None,
        help=f"输出文件路径；缺省取 TRAIN_TICKET_ACCOUNTS_FILE，再缺省为 {DEFAULT_OUTPUT}",
    )
    parser.add_argument("--base", default=None, help="网关地址，缺省取 TRAIN_TICKET_BASE / config.BASE_URL")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="单次请求超时（秒）")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="传输错误 / 5xx 的最大尝试次数")
    parser.add_argument("--backoff", type=float, default=DEFAULT_BACKOFF, help="重试退避基数（秒），指数增长")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要创建的账号，不发请求")
    parser.add_argument("--skip-preflight", action="store_true", help="跳过网关可达性探测")
    parser.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")

    args = parser.parse_args(argv)
    if args.count <= 0:
        parser.error("--count 必须为正整数")
    if args.start < 0:
        parser.error("--start 不能为负数")
    if args.retries < 1:
        parser.error("--retries 至少为 1")
    if args.timeout <= 0:
        parser.error("--timeout 必须为正数")
    if args.backoff < 0:
        parser.error("--backoff 不能为负数")
    return args


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )


# --------------------------------------------------------------------------- #
# 落盘
# --------------------------------------------------------------------------- #
def atomic_write_accounts(path: str, rows: Sequence[Dict[str, str]]) -> None:
    """原子写账号清单，避免进程被杀时留下半截 JSON。"""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(list(rows), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def json_object(response: requests.Response) -> Optional[dict]:
    """只在响应是 JSON 对象时返回 dict；数组、HTML、空响应一律返回 None。"""
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def post_json(
    session: requests.Session,
    url: str,
    payload: Dict[str, Any],
    *,
    timeout: float,
    retries: int,
    backoff: float,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, Optional[dict], str]:
    """POST JSON，对传输错误和 5xx 做指数退避重试。

    Returns:
        (status_code, body, note)。status_code 为 0 表示所有尝试都失败在传输层；
        body 仅在响应是 JSON 对象时非 None；note 为最后一次失败原因（成功时为空串）。
    """
    merged_headers = {"Content-Type": "application/json"}
    if headers:
        merged_headers.update(headers)

    last_status = 0
    last_note = ""
    for attempt in range(1, retries + 1):
        try:
            response = session.post(url, json=payload, headers=merged_headers, verify=False, timeout=timeout)
        except requests.RequestException as exc:
            last_status = 0
            last_note = f"{type(exc).__name__}: {exc}"
            retryable = True
        else:
            last_status = response.status_code
            body = json_object(response)
            if last_status >= 500:
                last_note = f"http={last_status} body={response.text[:200]!r}"
                retryable = True
            elif body is None:
                return last_status, None, f"http={last_status} 非 JSON 响应: {response.text[:200]!r}"
            else:
                return last_status, body, ""

        if not retryable or attempt == retries:
            break
        delay = backoff * (2 ** (attempt - 1))
        LOGGER.warning("请求失败，%d/%d 次尝试，%.1fs 后重试：%s（%s）", attempt, retries, delay, url, last_note)
        time.sleep(delay)

    return last_status, None, last_note


def probe_gateway(session: requests.Session, base: str, timeout: float) -> bool:
    """探测网关是否可达：能拿到任意 HTTP 响应即认为可达。"""
    url = f"{base.rstrip('/')}/api/v1/verifycode/generate"
    try:
        session.get(url, verify=False, timeout=timeout)
    except requests.RequestException as exc:
        LOGGER.error("网关探测失败 %s：%s: %s", url, type(exc).__name__, exc)
        return False
    return True


# --------------------------------------------------------------------------- #
# 业务动作
# --------------------------------------------------------------------------- #
def register_user(
    session: requests.Session,
    base: str,
    username: str,
    password: str,
    *,
    timeout: float,
    retries: int,
    backoff: float,
) -> Tuple[Optional[str], str]:
    """注册单个账号。返回 (userId, 失败原因)；userId 为 None 时原因非空。"""
    url = f"{base.rstrip('/')}/api/v1/userservice/users/register"
    payload = {
        "userName": username,
        "password": password,
        "gender": GENDER,
        "documentType": DOCUMENT_TYPE,
        # 用户表没有唯一约束，这里用用户名派生一个占位证件号，保证可读且不重复。
        "documentNum": f"U{username.replace('-', '')}",
        "email": f"{username}@uestc.test",
    }

    status, body, note = post_json(
        session, url, payload, timeout=timeout, retries=retries, backoff=backoff
    )
    if status == 0:
        return None, note
    if body is None:
        return None, note or f"http={status} 响应不可解析"
    if body.get("status") != 1:
        # 最常见的是重名（USER HAS ALREADY EXISTS），交给登录兜底。
        return None, f"http={status} status={body.get('status')} msg={body.get('msg')!r}"
    data = body.get("data")
    if not isinstance(data, dict) or not data.get("userId"):
        return None, f"http={status} status=1 但缺少 data.userId"
    return str(data["userId"]), ""


def login_user(
    session: requests.Session,
    base: str,
    username: str,
    password: str,
    *,
    timeout: float,
    retries: int,
    backoff: float,
) -> Tuple[Optional[str], str]:
    """登录并在失败时返回原因。用于已存在账号回填 userId，同时验证账号可用。"""
    root = base.rstrip("/")
    try:
        # 验证码 cookie 必须与登录请求同会话；即使集群不校验也保留这一步，保持与 _login 一致。
        session.get(f"{root}/api/v1/verifycode/generate", verify=False, timeout=timeout)
    except requests.RequestException as exc:
        return None, f"验证码接口不可达：{type(exc).__name__}: {exc}"

    status, body, note = post_json(
        session,
        f"{root}/api/v1/users/login",
        {"username": username, "password": password, "verificationCode": VERIFICATION_CODE},
        timeout=timeout,
        retries=retries,
        backoff=backoff,
        headers={
            "Origin": f"{root}/api/v1/users/login",
            "Referer": f"{root}/client_login.html",
        },
    )
    if status == 0:
        return None, note
    if body is None:
        return None, note or f"http={status} 响应不可解析"
    if body.get("status") != 1:
        return None, f"http={status} status={body.get('status')} msg={body.get('msg')!r}"
    data = body.get("data")
    if not isinstance(data, dict) or not data.get("userId"):
        return None, f"http={status} status=1 但缺少 data.userId"
    return str(data["userId"]), ""


def resolve_user(
    session: requests.Session,
    base: str,
    username: str,
    args: argparse.Namespace,
) -> Tuple[Optional[str], str]:
    """先注册，失败再登录兜底。返回 (userId, note)。"""
    common = {"timeout": args.timeout, "retries": args.retries, "backoff": args.backoff}

    uid, register_note = register_user(session, base, username, args.password, **common)
    if uid is not None:
        return uid, "register"

    LOGGER.info("%s 注册未成功（%s），改用登录兜底", username, register_note)
    uid, login_note = login_user(session, base, username, args.password, **common)
    if uid is not None:
        return uid, "login"
    return None, f"register: {register_note} | login: {login_note}"


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)

    base = (args.base or BASE_URL).rstrip("/")
    out = args.out or os.environ.get("TRAIN_TICKET_ACCOUNTS_FILE") or DEFAULT_OUTPUT
    usernames = build_usernames(args.prefix, args.count, args.start)

    LOGGER.info("base=%s", base)
    LOGGER.info("accounts=%d（%s … %s）out=%s", len(usernames), usernames[0], usernames[-1], out)
    if os.path.abspath(out) == os.path.abspath(DEFAULT_OUTPUT):
        LOGGER.info("提示：默认输出会覆盖仓库里的模板文件，可加 --out uestc_loadtest_accounts.local.json 避免脏 diff")

    if args.dry_run:
        for username in usernames:
            LOGGER.info("dry-run username=%s password=%s", username, args.password)
        return EXIT_OK

    session = requests.Session()
    session.headers.update({"Accept": "application/json", "User-Agent": "tt-loadtest-provisioner/1.0"})

    if not args.skip_preflight and not probe_gateway(session, base, timeout=min(PREFLIGHT_TIMEOUT, args.timeout)):
        LOGGER.error("网关不可达，请确认 TRAIN_TICKET_BASE 或实验室内网；确需跳过可用 --skip-preflight")
        return EXIT_GATEWAY_UNREACHABLE

    rows: List[Dict[str, str]] = []
    failures: List[str] = []
    try:
        for index, username in enumerate(usernames, 1):
            uid, note = resolve_user(session, base, username, args)
            if uid is None:
                LOGGER.error("[%d/%d] %s 失败：%s", index, len(usernames), username, note)
                failures.append(username)
                continue
            rows.append({"username": username, "password": args.password, "userId": uid})
            atomic_write_accounts(out, rows)
            LOGGER.info("[%d/%d] %s userId=%s（%s）", index, len(usernames), username, uid, note)
    except KeyboardInterrupt:
        LOGGER.warning("已中断：%d 个账号的结果保留在 %s", len(rows), out)
        return EXIT_INTERRUPTED

    if not rows:
        LOGGER.error("没有任何账号解析成功，未写 %s", out)
        return EXIT_FAILED
    if failures:
        LOGGER.error("完成 %d/%d，失败 %d 个：%s", len(rows), len(usernames), len(failures), ", ".join(failures))
        LOGGER.error("脚本幂等，重跑只会补齐失败/已存在的账号")
        return EXIT_FAILED

    LOGGER.info("完成 %d/%d，已写入 %s", len(rows), len(usernames), out)
    LOGGER.info("下一步：py -3.14 seed_contacts_uestc_loadtest.py")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
