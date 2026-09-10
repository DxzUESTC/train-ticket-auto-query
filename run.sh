#!/usr/bin/env bash
# 统一流量入口：预热与正式基线固化脚本
# 用法: ./run.sh smoke|warmup|baseline|all
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-}"
RUNS_DIR="runs"
mkdir -p "$RUNS_DIR"
TS="$(date +%Y%m%d-%H%M%S)"

export TRAIN_TICKET_BASE="${TRAIN_TICKET_BASE:-http://192.168.100.11:30467}"
export TRAFFIC_ENABLE_CONSIGN="${TRAFFIC_ENABLE_CONSIGN:-0}"
WARM_ITERS="${WARM_ITERS:-20}"
WARM_TIMEOUT="${WARM_TIMEOUT:-120}"
BASE_THREADS="${BASE_THREADS:-5}"
BASE_ITERS="${BASE_ITERS:-1200}"
BASE_TIMEOUT="${BASE_TIMEOUT:-15}"

usage() {
  cat <<'EOF'
用法: ./run.sh <smoke|warmup|baseline|all>
  smoke     1 线程 3 轮，超时 120s（连通性/接线检查）
  warmup    1 线程 20 轮，超时 120s（冷启动预热，结束后校验无 exception/http_fail）
  baseline  5 线程 1200 轮，超时 15s（正式基线）
  all       warmup 通过后自动执行 baseline

可覆盖环境变量:
  WARM_ITERS WARM_TIMEOUT BASE_THREADS BASE_ITERS BASE_TIMEOUT
  TRAIN_TICKET_BASE TRAFFIC_ENABLE_CONSIGN TRAFFIC_HTTP_TIMEOUT
EOF
}

check_python() {
  command -v python3 >/dev/null 2>&1 || { echo "错误: 未找到 python3"; exit 1; }
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else "错误: 需要 Python >= 3.7，当前 %s" % sys.version.split()[0])'
}

run_case() {
  local name="$1" threads="$2" iters="$3" timeout="$4"
  local stats="$RUNS_DIR/$TS-$name-stats.json"
  local log="$RUNS_DIR/$TS-$name.log"
  echo ">>> $name: LOAD_THREADS=$threads ITER=$iters TIMEOUT=${timeout}s"
  echo ">>> stats=$stats"
  echo ">>> log=$log"
  LOAD_THREADS="$threads" \
  TRAFFIC_INNER_ITERATIONS="$iters" \
  TRAFFIC_HTTP_TIMEOUT="$timeout" \
  TRAFFIC_STATS_JSON="$stats" \
  python3 normal_request_manager.py 2>&1 | tee "$log"
}

check_warmup() {
  python3 - "$1" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    snap = json.load(f)

bad = [
    f"{step}: exception={s['exception']} http_fail={s['http_fail']}"
    for step, s in snap["steps"].items()
    if s["exception"] or s["http_fail"]
]
if bad:
    print("预热失败，中止：")
    print("\n".join(bad))
    sys.exit(1)
print("预热通过：无 exception/http_fail")
PY
}

warn_midnight() {
  local hh mm
  hh="$(date +%H)"
  mm="$(date +%M)"
  if [ "$hh" -ge 23 ] && [ "$mm" -ge 30 ]; then
    echo "警告: 当前时间接近午夜，长跑跨天后查票会全空，建议改期或 0 点后重启进程。"
  fi
}

case "$MODE" in
  smoke)
    check_python
    run_case smoke 1 3 "$WARM_TIMEOUT"
    ;;
  warmup)
    check_python
    run_case warmup 1 "$WARM_ITERS" "$WARM_TIMEOUT"
    check_warmup "$RUNS_DIR/$TS-warmup-stats.json"
    ;;
  baseline)
    check_python
    warn_midnight
    run_case baseline "$BASE_THREADS" "$BASE_ITERS" "$BASE_TIMEOUT"
    ;;
  all)
    check_python
    warn_midnight
    run_case warmup 1 "$WARM_ITERS" "$WARM_TIMEOUT"
    check_warmup "$RUNS_DIR/$TS-warmup-stats.json"
    run_case baseline "$BASE_THREADS" "$BASE_ITERS" "$BASE_TIMEOUT"
    ;;
  *)
    usage
    exit 1
    ;;
esac
