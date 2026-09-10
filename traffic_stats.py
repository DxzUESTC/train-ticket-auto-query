"""并发流量的分步业务统计：用于「运行正常」验收与故障注入前基线对比。

口径：
- 每个业务步骤记录 attempt 以及 success/partial/business_fail/http_fail/exception/skip；
- 所有写操作线程安全；normal_request_manager 结束后打印汇总；
- 设置 TRAFFIC_STATS_JSON 时额外落盘 JSON，便于归档为实验证据。
"""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from typing import Dict, List, Optional

OUTCOMES = ("success", "partial", "business_fail", "http_fail", "exception", "skip")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def _percentile(values: List[float], q: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))
    return ordered[idx]


class TrafficStats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._steps: "OrderedDict[str, Dict]" = OrderedDict()
        self.started_at = _now()
        self.finished_at: Optional[str] = None

    def record(
        self,
        step: str,
        outcome: str,
        latency_ms: Optional[float] = None,
        detail: str = "",
    ) -> None:
        if outcome not in OUTCOMES:
            raise ValueError(f"unknown outcome: {outcome}")
        with self._lock:
            s = self._steps.setdefault(
                step,
                {
                    "attempt": 0,
                    **{o: 0 for o in OUTCOMES},
                    "latency_ms": [],
                    "last_detail": "",
                },
            )
            s["attempt"] += 1
            s[outcome] += 1
            if latency_ms is not None:
                s["latency_ms"].append(round(float(latency_ms), 1))
            if detail:
                s["last_detail"] = str(detail)[:300]

    def finish(self) -> None:
        with self._lock:
            self.finished_at = _now()

    def snapshot(self) -> Dict:
        with self._lock:
            steps: Dict[str, Dict] = {}
            for name, s in self._steps.items():
                lat = s["latency_ms"]
                steps[name] = {
                    **{k: v for k, v in s.items() if k != "latency_ms"},
                    "p50_ms": _percentile(lat, 0.50),
                    "p95_ms": _percentile(lat, 0.95),
                }
            return {
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "steps": steps,
            }

    def render_summary(self) -> str:
        snap = self.snapshot()

        def fmt(v: Optional[float]) -> str:
            return "-" if v is None else f"{v:.0f}"

        lines = [
            "========== traffic stats ==========",
            f"start: {snap['started_at']}",
            f"end:   {snap['finished_at']}",
            (
                f"{'step':<18}{'attempt':>8}{'success':>8}{'partial':>8}"
                f"{'bizfail':>8}{'httpfail':>9}{'except':>7}{'skip':>6}{'p50ms':>8}{'p95ms':>8}"
            ),
        ]
        for name, s in snap["steps"].items():
            lines.append(
                f"{name:<18}{s['attempt']:>8}{s['success']:>8}{s['partial']:>8}"
                f"{s['business_fail']:>8}{s['http_fail']:>9}{s['exception']:>7}"
                f"{s['skip']:>6}{fmt(s['p50_ms']):>8}{fmt(s['p95_ms']):>8}"
            )
        lines.append("===================================")
        return "\n".join(lines)

    def dump_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)


STATS = TrafficStats()
