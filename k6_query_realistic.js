/**
 * k6 开环压测：真实业务混合的查票流量
 *
 * 与 k6_query_smoke.js 的区别：
 *   1. 只使用 2026-11-07 实测「有车次返回」的 OD 组合，避免请求打在空线路上空转；
 *   2. 按业务比例混合 4 个查票接口（高铁查票 / 普速查票 / 智能推荐 cheapest / quickest），
 *      智能推荐会扇出到 travel + travel2 + basic + seat + price，产生的 trace 更接近真实业务；
 *   3. 日期在「今天 / 明天」之间随机，贴近真实用户行为；
 *   4. 每个接口打 endpoint 标签，summary 里能分开看各接口的延迟。
 *
 * 用法（在 VM 上）：
 *   BASE_URL=http://192.168.100.11:30467 RATE=10 DURATION=2m k6 run k6_query_realistic.js
 */
import http from 'k6/http';
import { check } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter } from 'k6/metrics';

const BASE = (__ENV.BASE_URL || 'http://192.168.100.11:30467').replace(/\/+$/, '');
const ACCOUNTS_FILE = __ENV.ACCOUNTS_FILE || './uestc_loadtest_accounts.json';
const RATE = Number(__ENV.RATE || 10);
const DURATION = __ENV.DURATION || '2m';
const PRE_VUS = Number(__ENV.PRE_VUS || 30);
const MAX_VUS = Number(__ENV.MAX_VUS || 100);
const TIMEOUT = __ENV.TIMEOUT || '15s';

const emptyData = new Counter('empty_data_responses');

const accounts = new SharedArray('accounts', function () {
  return JSON.parse(open(ACCOUNTS_FILE));
});

// 智能推荐类接口对以下 OD 都能返回结果
const PLAN_PAIRS = [
  ['shanghai', 'suzhou'],
  ['suzhou', 'shanghai'],
  ['shanghai', 'nanjing'],
  ['nanjing', 'shanghai'],
  ['nanjing', 'zhenjiang'],
  ['wuxi', 'suzhou'],
  ['shanghaihongqiao', 'hangzhou'],
];

// weight 为相对权重（合计 100），pairs 只放实测有车次的组合
const ENDPOINTS = [
  {
    name: 'hs_left',
    path: '/api/v1/travelservice/trips/left',
    weight: 60,
    pairs: [
      ['shanghai', 'suzhou'],
      ['suzhou', 'shanghai'],
      ['nanjing', 'shanghai'],
      ['nanjing', 'zhenjiang'],
      ['wuxi', 'suzhou'],
    ],
  },
  {
    name: 'normal_left',
    path: '/api/v1/travel2service/trips/left',
    weight: 15,
    pairs: [
      ['shanghai', 'nanjing'],
      ['nanjing', 'shanghai'],
      ['nanjing', 'xuzhou'],
      ['jinan', 'beijing'],
    ],
  },
  {
    name: 'plan_cheapest',
    path: '/api/v1/travelplanservice/travelPlan/cheapest',
    weight: 15,
    pairs: PLAN_PAIRS,
  },
  {
    name: 'plan_quickest',
    path: '/api/v1/travelplanservice/travelPlan/quickest',
    weight: 10,
    pairs: PLAN_PAIRS,
  },
];

// 展开成权重槽位，O(1) 抽样
const SLOTS = [];
for (let i = 0; i < ENDPOINTS.length; i++) {
  for (let w = 0; w < ENDPOINTS[i].weight; w++) {
    SLOTS.push(i);
  }
}

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
  thresholds: {
    // 只为在 summary 里分行展示各接口延迟；数值放宽，避免注入实验时误判退出
    'http_req_duration{endpoint:hs_left}': ['p(95)<8000'],
    'http_req_duration{endpoint:normal_left}': ['p(95)<8000'],
    'http_req_duration{endpoint:plan_cheapest}': ['p(95)<8000'],
    'http_req_duration{endpoint:plan_quickest}': ['p(95)<8000'],
  },
};

function departureDate() {
  if (__ENV.DEPARTURE_DATE) {
    return __ENV.DEPARTURE_DATE;
  }
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  const today = new Date(local.getTime());
  if (Math.random() < 0.5) {
    return today.toISOString().slice(0, 10);
  }
  const tomorrow = new Date(local.getTime() + 24 * 3600 * 1000);
  return tomorrow.toISOString().slice(0, 10);
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
  console.log(`login ok=${tokens.length} failed=${failed.length}`);
  if (tokens.length === 0) {
    throw new Error(`no account could login; check BASE_URL=${BASE} and ${ACCOUNTS_FILE}`);
  }
  return { tokens };
}

export default function (data) {
  const tokens = data.tokens;
  const account = tokens[(__VU - 1) % tokens.length];
  const endpoint = ENDPOINTS[SLOTS[Math.floor(Math.random() * SLOTS.length)]];
  const pair = endpoint.pairs[Math.floor(Math.random() * endpoint.pairs.length)];

  const res = http.post(
    `${BASE}${endpoint.path}`,
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
      tags: { endpoint: endpoint.name },
      timeout: TIMEOUT,
    },
  );

  let body = null;
  try {
    body = res.json();
  } catch (e) {
    body = null;
  }
  const ok = res.status === 200 && body && body.status === 1;
  if (ok && body.data != null && !(Array.isArray(body.data) && body.data.length === 0)) {
    // 有数据，正常
  } else if (ok) {
    emptyData.add(1, { endpoint: endpoint.name });
  }

  check(res, {
    'status is 200': (r) => r.status === 200,
    'business status is 1': () => !!ok,
    'has data': () => !!ok && body.data != null && !(Array.isArray(body.data) && body.data.length === 0),
  });
}
