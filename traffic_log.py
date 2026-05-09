"""
并发流量下的统一控制台输出：带工作线程槽位、OS 线程号、当前账号与 idx，便于对齐 500 等日志。
仅在设置了 set_traffic_context 的迭代内会带 W/user/idx；单独跑脚本时仍有 tid。
"""

from __future__ import annotations

import threading
from typing import Optional

_tls = threading.local()


def set_traffic_context(worker_id: int, username: str, account_idx: int) -> None:
    _tls.worker_id = int(worker_id)
    _tls.username = username
    _tls.account_idx = int(account_idx)


def clear_traffic_context() -> None:
    for k in ("worker_id", "username", "account_idx"):
        if hasattr(_tls, k):
            delattr(_tls, k)


def _native_tid() -> int:
    t = threading.current_thread()
    nid = getattr(t, "native_id", None)
    if nid is not None:
        return int(nid)
    return int(threading.get_ident())


def traffic_prefix() -> str:
    parts: list[str] = []
    wid: Optional[int] = getattr(_tls, "worker_id", None)
    if wid is not None:
        parts.append(f"W{wid}")
    parts.append(f"tid={_native_tid()}")
    un = getattr(_tls, "username", None)
    if un:
        parts.append(f"user={un}")
    idx = getattr(_tls, "account_idx", None)
    if idx is not None:
        parts.append(f"idx={idx}")
    return "[" + " ".join(parts) + "]"


def detail_indent() -> int:
    """在 normal_request_manager 设置的迭代上下文内，子步骤用更大缩进；单独跑脚本时为 0。"""
    return 2 if getattr(_tls, "worker_id", None) is not None else 0


def phase_indent() -> int:
    """迭代内一级步骤（查单、支付等）缩进。"""
    return 1 if getattr(_tls, "worker_id", None) is not None else 0


def tlog(msg: str, indent: int = 0) -> None:
    pad = "  " * max(0, indent)
    print(f"{pad}{traffic_prefix()} {msg}")
