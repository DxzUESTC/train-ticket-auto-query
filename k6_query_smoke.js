/**
 * k6 开环压测：只读查票（第 0 步：连通性 + 基线 RPC）
 *
 * 为什么用 constant-arrival-rate：开环模型按固定速率发请求，不等上一个响应返回。
 * 故障注入导致延迟上升时，到达率保持不变，因此「吞吐下降」不会被误读成「负载下降」，
 * 延迟和错误率才是干净的观测信号。代价是 VU 必须预留足够，否则 dropped_iterations 会上升。
 *
 * 用法（在 VM 上，脚本与 uestc_loadtest_accounts.json 同目录）：
 *   BASE_URL=http://192.168.100.11:30467 RATE=20 DURATION=2m \
 *     k6 run k6_query_smoke.js
 *
 * 常用环境变量：
 *   BASE_URL        网关地址，默认 http://192.168.100.11:30467
 *   ACCOUNTS_FILE   账号表路径，默认 ./uestc_loadtest_accounts.json
 *   RATE            每秒请求数，默认 5
 *   DURATION        持续时间，默认 1m
 *   PRE_VUS/MAX_VUS 预分配 / 最大 VU 数，默认 20 / 100
 *   DEPARTURE_DATE  出发日期 YYYY-MM-DD，默认服务器当天
 */
import http from 'k6/http';
import { check } from 'k6';
import { SharedArray } from 'k6/data';

const BASE = (__ENV.BASE_URL || 'http://192.168.100.11:30467').replace(/\/+$/, '');
const ACCOUNTS_FILE = __ENV.ACCOUNTS_FILE || './uestc_loadtest_accounts.json';
const RATE = Number(__ENV.RATE || 5);
const DURATION = __ENV.DURATION || '1m';
const PRE_VUS = Number(__ENV.PRE_VUS || 20);
const MAX_VUS = Number(__ENV.MAX_VUS || 100);

// 与 seed_od.py 中高铁线路一致的 OD（小写、无空格）
const PLACE_PAIRS = [
  ['shanghai', 'suzhou'],
  ['suzhou', 'shanghai'],
  ['shanghai', 'nanjing'],
  ['nanjing', 'shanghai'],
];

const accounts = new SharedArray('accounts', function () {
  return JSON.parse(open(ACCOUNTS_FILE));
});

export const options = {
  scenarios: {
    query: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: PRE_VUS,
      maxVUs: MAX_VUS,
      tags: { scenario: 'query' },
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

function departureDate() {
  if (__ENV.DEPARTURE_DATE) {
    return __ENV.DEPARTURE_DATE;
  }
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

export function setup() {
  const tokens = [];
  const failed = [];

  for (let i = 0; i < accounts.length; i++) {
    const account = accounts[i];
    const res = http.post(
      `${BASE}/api/v1/users/login`,
      JSON.stringify({ username: account.username, password: account.password }),
      {
        headers: { 'Content-Type': 'application/json' },
        tags: { step: 'login' },
        timeout: '10s',
      },
    );

    let body = null;
    try {
      body = res.json();
    } catch (e) {
      body = null;
    }
    if (res.status === 200 && body && body.status === 1 && body.data && body.data.token) {
      tokens.push({ username: account.username, token: body.data.token });
    } else {
      failed.push(account.username);
    }
  }

  console.log(
    `login ok=${tokens.length} failed=${failed.length}` +
      (failed.length ? ` first_failed=${failed.slice(0, 5).join(',')}` : ''),
  );
  if (tokens.length === 0) {
    throw new Error(`no account could login; check BASE_URL=${BASE} and ${ACCOUNTS_FILE}`);
  }
  return { tokens };
}

export default function (data) {
  const tokens = data.tokens;
  const account = tokens[(__VU - 1) % tokens.length];
  const pair = PLACE_PAIRS[Math.floor(Math.random() * PLACE_PAIRS.length)];

  const res = http.post(
    `${BASE}/api/v1/travelservice/trips/left`,
    JSON.stringify({
      departureTime: departureDate(),
      startPlace: pair[0],
      endPlace: pair[1],
    }),
    {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${account.token}`,
      },
      tags: { step: 'query' },
      timeout: '10s',
    },
  );

  check(res, {
    'status is 200': (r) => r.status === 200,
    'business status is 1': (r) => {
      try {
        const body = r.json();
        return body && body.status === 1;
      } catch (e) {
        return false;
      }
    },
  });
}
