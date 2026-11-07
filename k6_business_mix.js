/**
 * k6 开环压测：业务混合负载（查票 + 下单 + 支付 + 出票 + 进站 + 取消）
 *
 * 覆盖的服务：
 *   query   场景 → ts-travel-service / ts-travel2-service / ts-travelplan-service
 *   business 场景 → ts-travel-service、ts-contacts-service、ts-assurance-service、
 *                   ts-preserve-service、ts-order-service、ts-inside-payment-service、
 *                   ts-execute-service、ts-cancel-service、ts-consign-service(可选)
 *
 * 关键点（与 Python 的 query_and_preserve / normal_request_manager 对齐）：
 *   1. preserve 不返回 orderId，必须用 orders/refresh 的前后 id 差集找出新订单；
 *   2. business 分支按概率走「支付→出票→进站」或「取消」，与真实用户行为一致；
 *   3. 每个 VU 绑定一个独立账号（VU 数 ≤ 账号数），避免同一账号并发下单互相干扰。
 *
 * 用法（在 VM 上）：
 *   BASE_URL=http://192.168.100.11:30467 RATE_QUERY=8 RATE_BOOK=1 DURATION=5m \
 *     k6 run k6_business_mix.js
 */
import http from 'k6/http';
import { check } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter } from 'k6/metrics';

const BASE = (__ENV.BASE_URL || 'http://192.168.100.11:30467').replace(/\/+$/, '');
const ACCOUNTS_FILE = __ENV.ACCOUNTS_FILE || './uestc_loadtest_accounts.json';
const DURATION = __ENV.DURATION || '5m';
const RATE_QUERY = Number(__ENV.RATE_QUERY || 8);
const RATE_BOOK = Number(__ENV.RATE_BOOK || 1);
const BOOK_PERIOD = __ENV.BOOK_PERIOD || '1s'; // 下单速率的时间单位，k6 的 rate 必须是整数
const PRE_VUS_QUERY = Number(__ENV.PRE_VUS_QUERY || 20);
const MAX_VUS_QUERY = Number(__ENV.MAX_VUS_QUERY || 40);
const PRE_VUS_BOOK = Number(__ENV.PRE_VUS_BOOK || 10);
const MAX_VUS_BOOK = Number(__ENV.MAX_VUS_BOOK || 20);
const P_PAY = Number(__ENV.P_PAY || 0.7);      // 下单后走支付链路的概率，其余走取消
const P_CONSIGN = Number(__ENV.P_CONSIGN || 0.2); // 下单时附带托运的概率
// 账号偏移：uestc-test1..10 是历史账号（订单很多，refresh 响应会很大），默认从第 11 个开始用
const ACCOUNT_OFFSET = Number(__ENV.ACCOUNT_OFFSET || 10);

const orderFail = new Counter('order_chain_fail');
const noTrips = new Counter('no_trips');
const emptyData = new Counter('empty_data_responses');

const accounts = new SharedArray('accounts', function () {
  return JSON.parse(open(ACCOUNTS_FILE));
});

const PLAN_PAIRS = [
  ['shanghai', 'suzhou'], ['suzhou', 'shanghai'], ['shanghai', 'nanjing'],
  ['nanjing', 'shanghai'], ['nanjing', 'zhenjiang'], ['wuxi', 'suzhou'],
  ['shanghaihongqiao', 'hangzhou'],
];

const QUERY_ENDPOINTS = [
  {
    name: 'hs_left', path: '/api/v1/travelservice/trips/left', weight: 60,
    pairs: [['shanghai', 'suzhou'], ['suzhou', 'shanghai'], ['nanjing', 'shanghai'],
            ['nanjing', 'zhenjiang'], ['wuxi', 'suzhou']],
  },
  {
    name: 'normal_left', path: '/api/v1/travel2service/trips/left', weight: 15,
    pairs: [['shanghai', 'nanjing'], ['nanjing', 'shanghai'], ['nanjing', 'xuzhou'], ['jinan', 'beijing']],
  },
  { name: 'plan_cheapest', path: '/api/v1/travelplanservice/travelPlan/cheapest', weight: 15, pairs: PLAN_PAIRS },
  { name: 'plan_quickest', path: '/api/v1/travelplanservice/travelPlan/quickest', weight: 10, pairs: PLAN_PAIRS },
];

const SLOTS = [];
for (let i = 0; i < QUERY_ENDPOINTS.length; i++) {
  for (let w = 0; w < QUERY_ENDPOINTS[i].weight; w++) SLOTS.push(i);
}

// 高铁下单用这对 OD（实测稳定有车次）
const BOOK_PAIRS = [
  ['shanghai', 'suzhou'],
  ['suzhou', 'shanghai'],
  ['nanjing', 'shanghai'],
];

export const options = {
  scenarios: {
    query: {
      executor: 'constant-arrival-rate',
      exec: 'queryFlow',
      rate: RATE_QUERY,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: PRE_VUS_QUERY,
      maxVUs: MAX_VUS_QUERY,
      tags: { scenario: 'query' },
    },
    business: {
      executor: 'constant-arrival-rate',
      exec: 'businessFlow',
      rate: RATE_BOOK,
      timeUnit: BOOK_PERIOD,
      duration: DURATION,
      preAllocatedVUs: PRE_VUS_BOOK,
      maxVUs: MAX_VUS_BOOK,
      tags: { scenario: 'business' },
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  thresholds: {
    // 只为在 summary 里按步骤分行展示延迟；上限放宽，避免注入实验时误判退出
    'http_req_duration{step:book_query}': ['p(95)<30000'],
    'http_req_duration{step:contacts}': ['p(95)<30000'],
    'http_req_duration{step:preserve}': ['p(95)<30000'],
    'http_req_duration{step:orders_refresh}': ['p(95)<30000'],
    'http_req_duration{step:pay}': ['p(95)<30000'],
    'http_req_duration{step:collect}': ['p(95)<30000'],
    'http_req_duration{step:enter_station}': ['p(95)<30000'],
    'http_req_duration{step:cancel}': ['p(95)<30000'],
  },
};

function localDate(offsetDays) {
  if (__ENV.DEPARTURE_DATE) return __ENV.DEPARTURE_DATE;
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000 + offsetDays * 86400000);
  return local.toISOString().slice(0, 10);
}

function randomDate() {
  return localDate(Math.random() < 0.5 ? 0 : 1);
}

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

function jsonOf(res) {
  try {
    return res.json();
  } catch (e) {
    return null;
  }
}

export function setup() {
  const list = [];
  let failed = 0;
  for (let i = 0; i < accounts.length; i++) {
    const acc = accounts[i];
    const res = http.post(
      `${BASE}/api/v1/users/login`,
      JSON.stringify({ username: acc.username, password: acc.password }),
      { headers: { 'Content-Type': 'application/json' }, tags: { step: 'login' }, timeout: '10s' },
    );
    const body = jsonOf(res);
    if (res.status !== 200 || !body || body.status !== 1 || !body.data) {
      failed += 1;
      continue;
    }
    list.push({ username: acc.username, userId: body.data.userId, token: body.data.token });
  }
  console.log(`login ok=${list.length} failed=${failed}`);
  if (list.length === 0) throw new Error('no account could login');
  return { accounts: list };
}

function authHeaders(account) {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${account.token}`,
  };
}

function queryTrips(account, startPlace, endPlace, dep) {
  const res = http.post(
    `${BASE}/api/v1/travelservice/trips/left`,
    JSON.stringify({ departureTime: dep, startPlace, endPlace }),
    { headers: authHeaders(account), tags: { step: 'book_query' }, timeout: '15s' },
  );
  const body = jsonOf(res);
  if (res.status !== 200 || !body || body.status !== 1 || !Array.isArray(body.data) || body.data.length === 0) {
    return null;
  }
  return body.data;
}

function refreshOrders(account) {
  const res = http.post(
    `${BASE}/api/v1/orderservice/order/refresh`,
    JSON.stringify({ loginId: account.userId }),
    { headers: authHeaders(account), tags: { step: 'orders_refresh' }, timeout: '20s' },
  );
  const body = jsonOf(res);
  if (res.status !== 200 || !body || body.status !== 1 || !Array.isArray(body.data)) {
    return null;
  }
  return body.data;
}

function orderIds(orders) {
  const ids = {};
  for (let i = 0; i < orders.length; i++) {
    if (orders[i].id) ids[orders[i].id] = true;
  }
  return ids;
}

function postStep(account, path, payload, step, timeout) {
  const res = http.post(`${BASE}${path}`, JSON.stringify(payload), {
    headers: authHeaders(account),
    tags: { step },
    timeout: timeout || '20s',
  });
  return { res, body: jsonOf(res) };
}

function getStep(account, path, step, timeout) {
  const res = http.get(`${BASE}${path}`, {
    headers: authHeaders(account),
    tags: { step },
    timeout: timeout || '20s',
  });
  return { res, body: jsonOf(res) };
}

/* ------------------------------ 场景 1：查票 ------------------------------ */
export function queryFlow(data) {
  const account = data.accounts[(__VU - 1 + ACCOUNT_OFFSET) % data.accounts.length];
  const endpoint = QUERY_ENDPOINTS[SLOTS[Math.floor(Math.random() * SLOTS.length)]];
  const pair = pick(endpoint.pairs);

  const res = http.post(
    `${BASE}${endpoint.path}`,
    JSON.stringify({ departureTime: randomDate(), startPlace: pair[0], endPlace: pair[1] }),
    { headers: authHeaders(account), tags: { endpoint: endpoint.name }, timeout: '15s' },
  );
  const body = jsonOf(res);
  const ok = res.status === 200 && body && body.status === 1;
  if (ok && (body.data == null || (Array.isArray(body.data) && body.data.length === 0))) {
    emptyData.add(1, { endpoint: endpoint.name });
  }
  check(res, {
    'query: status 200': (r) => r.status === 200,
    'query: business ok': () => !!ok,
  });
}

/* --------------------------- 场景 2：完整业务链 --------------------------- */
export function businessFlow(data) {
  const account = data.accounts[(__VU - 1 + ACCOUNT_OFFSET) % data.accounts.length];
  const dep = localDate(Math.random() < 0.5 ? 0 : 1);
  const pair = pick(BOOK_PAIRS);

  // 1. 查票
  const trips = queryTrips(account, pair[0], pair[1], dep);
  check(trips, { 'book: has trips': (t) => t && t.length > 0 });
  if (!trips) {
    noTrips.add(1);
    return;
  }
  const trip = pick(trips).tripId;
  const tripId = `${trip.type}${trip.number}`;

  // 2. 联系人（真实页面订票页会查）
  const contacts = getStep(account, `/api/v1/contactservice/contacts/account/${account.userId}`, 'contacts');
  const contactList = contacts.body && Array.isArray(contacts.body.data) ? contacts.body.data : [];
  if (contactList.length === 0) {
    orderFail.add(1, { reason: 'no_contact' });
    return;
  }
  const contactId = pick(contactList).id;

  // 3. 保险类型（真实页面会查）
  getStep(account, '/api/v1/assuranceservice/assurances/types', 'assurance');

  // 4. 下单前记录订单 id 集合
  const before = refreshOrders(account);
  if (!before) {
    orderFail.add(1, { reason: 'refresh_before' });
    return;
  }
  const beforeIds = orderIds(before);

  // 5. 下单
  const payload = {
    accountId: account.userId,
    assurance: Math.random() < 0.5 ? 1 : 0,
    contactsId: contactId,
    date: dep,
    from: pair[0],
    to: pair[1],
    tripId,
    seatType: pick([2, 3]),
    foodType: 0,
  };
  if (Math.random() < P_CONSIGN) {
    payload.consigneeName = 'loadtest';
    payload.consigneePhone = '139' + String(Math.floor(Math.random() * 100000000)).padStart(8, '0');
    payload.consigneeWeight = 1 + Math.floor(Math.random() * 10);
    payload.handleDate = dep;
  }

  const preserve = postStep(account, '/api/v1/preserveservice/preserve', payload, 'preserve', '30s');
  const preserved = preserve.res.status === 200 && preserve.body && preserve.body.status === 1;
  check(preserve.res, {
    'book: preserve ok': () => !!preserved,
  });
  if (!preserved) {
    orderFail.add(1, { reason: 'preserve_failed' });
    return;
  }

  // 6. 找新订单
  const after = refreshOrders(account);
  if (!after) {
    orderFail.add(1, { reason: 'refresh_after' });
    return;
  }
  let newOrder = null;
  for (let i = 0; i < after.length; i++) {
    if (after[i].id && !beforeIds[after[i].id]) {
      newOrder = after[i];
      break;
    }
  }
  if (!newOrder) {
    orderFail.add(1, { reason: 'order_not_found' });
    return;
  }

  // 7. 分支：支付链路 或 取消
  if (Math.random() < P_PAY) {
    const pay = postStep(account, '/api/v1/inside_pay_service/inside_payment',
      { orderId: newOrder.id, tripId }, 'pay');
    const paid = pay.res.status === 200 && pay.body && pay.body.status === 1 &&
      String(pay.body.msg || '').startsWith('Payment Success');
    check(pay.res, { 'book: pay ok': () => !!paid });
    if (!paid) {
      orderFail.add(1, { reason: 'pay_failed' });
      return;
    }

    const collect = getStep(account, `/api/v1/executeservice/execute/collected/${newOrder.id}`, 'collect');
    const collected = collect.res.status === 200 && collect.body && collect.body.status === 1;
    check(collect.res, { 'book: collect ok': () => !!collected });
    if (!collected) {
      orderFail.add(1, { reason: 'collect_failed' });
      return;
    }

    const enter = getStep(account, `/api/v1/executeservice/execute/execute/${newOrder.id}`, 'enter_station');
    const entered = enter.res.status === 200 && enter.body && enter.body.status === 1;
    check(enter.res, { 'book: enter ok': () => !!entered });
    if (!entered) orderFail.add(1, { reason: 'enter_failed' });
  } else {
    const cancel = getStep(
      account,
      `/api/v1/cancelservice/cancel/${newOrder.id}/${account.userId}`,
      'cancel',
      '30s',
    );
    const cancelled = cancel.res.status === 200 && cancel.body && cancel.body.status === 1;
    check(cancel.res, { 'book: cancel ok': () => !!cancelled });
    if (!cancelled) orderFail.add(1, { reason: 'cancel_failed' });
  }
}
