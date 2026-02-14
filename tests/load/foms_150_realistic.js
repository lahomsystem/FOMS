import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const status2xxRate = new Rate('status_2xx_rate');
const status429Rate = new Rate('status_429_rate');
const status5xxRate = new Rate('status_5xx_rate');
const authFailRate = new Rate('status_auth_fail_rate');
const requestCount = new Counter('scenario_request_count');

// Detailed trace metrics (by tags: flow/route/method/status)
const endpointRequestCount = new Counter('endpoint_request_count');
const endpointFailCount = new Counter('endpoint_fail_count');
const endpoint429Count = new Counter('endpoint_429_count');
const endpoint5xxCount = new Counter('endpoint_5xx_count');
const endpointAuthFailCount = new Counter('endpoint_auth_fail_count');
const endpointDuration = new Trend('endpoint_req_duration', true);

const BASE_URL = (__ENV.BASE_URL || 'http://localhost:5000').replace(/\/+$/, '');
const COOKIE_NAME = __ENV.COOKIE_NAME || 'session_staging';
const TARGET_USERS = Number(__ENV.TARGET_USERS || 150);
const TEST_DURATION = __ENV.TEST_DURATION || '20m';
const STRICT_COOKIE_POOL = (__ENV.STRICT_COOKIE_POOL || 'true').toLowerCase() === 'true';
const DISCARD_RESPONSE_BODIES = (__ENV.DISCARD_RESPONSE_BODIES || 'true').toLowerCase() === 'true';

const ERP_WEIGHT = Number(__ENV.ERP_WEIGHT || 0.5);
const CHAT_WEIGHT = Number(__ENV.CHAT_WEIGHT || 0.25);
const FILE_WEIGHT = Number(__ENV.FILE_WEIGHT || 0.05);
const IDLE_WEIGHT = Number(__ENV.IDLE_WEIGHT || 0.2);

const TRACE_ERRORS = (__ENV.TRACE_ERRORS || 'true').toLowerCase() === 'true';
const TRACE_ERROR_SAMPLE_RATE = Number(__ENV.TRACE_ERROR_SAMPLE_RATE || 0.2);
const TRACE_MAX_ERROR_LOGS = Number(__ENV.TRACE_MAX_ERROR_LOGS || 120);
const TRACE_SUMMARY_JSON = __ENV.TRACE_SUMMARY_JSON || 'tests/load/last_trace_summary.json';
const TRACE_SUMMARY_TXT = __ENV.TRACE_SUMMARY_TXT || 'tests/load/last_trace_summary.txt';
const SHIPMENT_DATE = __ENV.SHIPMENT_DATE || new Date(Date.now() + 9 * 60 * 60 * 1000).toISOString().slice(0, 10);

const CHAT_ROOM_ID = __ENV.CHAT_ROOM_ID || '';
const CHAT_DOWNLOAD_KEY = __ENV.CHAT_DOWNLOAD_KEY || '';

let errorLogCount = 0;
let storageConfigHintLogged = false;

const dashboardRoutes = [
  { name: 'erp_dashboard', path: '/erp/dashboard' },
  { name: 'erp_production_dashboard', path: '/erp/production/dashboard' },
  { name: 'erp_construction_dashboard', path: '/erp/construction/dashboard' },
  { name: 'erp_measurement_page', path: '/erp/measurement' },
  // /erp/shipment 은 date 파라미터로 302 redirect 되므로, 기본부터 date를 붙여 불필요한 302를 제거
  { name: 'erp_shipment_page', path: `/erp/shipment?date=${SHIPMENT_DATE}` },
];

const erpApiRoutes = [
  { name: 'notif_badge', path: '/erp/api/notifications/badge' },
  { name: 'notif_list', path: '/erp/api/notifications?limit=10' },
  { name: 'orders_list', path: '/api/orders?limit=200' },
  { name: 'chat_rooms_list', path: '/api/chat/rooms' },
];

const uploadBytes = open('./fixtures/upload_sample.txt', 'b');

function randomItem(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function parseCookiePool(raw) {
  if (!raw) return [];
  return raw
    .replace(/\r/g, '\n')
    .split('\n')
    .flatMap((line) => line.split(/[|,;]/))
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .filter((line) => !line.startsWith('#'))
    .map((line) => {
      // 허용: "session_staging=<cookie>" 혹은 "<cookie>"
      if (line.startsWith(`${COOKIE_NAME}=`)) {
        return line.slice(COOKIE_NAME.length + 1).trim();
      }
      return line;
    })
    .filter((v) => v.length > 0);
}

function loadCookieFile() {
  try {
    return open('./session_cookies.txt');
  } catch (e) {
    return '';
  }
}

const ENV_COOKIE_POOL = parseCookiePool(__ENV.SESSION_COOKIES || '');
const FILE_COOKIE_POOL = parseCookiePool(loadCookieFile());
const SINGLE_COOKIE = (__ENV.SESSION_COOKIE || '').trim();

const SESSION_POOL = [...new Set([...ENV_COOKIE_POOL, ...FILE_COOKIE_POOL, ...(SINGLE_COOKIE ? [SINGLE_COOKIE] : [])])];

if (SESSION_POOL.length === 0) {
  throw new Error(
    'No session cookies found. Set SESSION_COOKIE or SESSION_COOKIES, or create tests/load/session_cookies.txt',
  );
}
if (STRICT_COOKIE_POOL && SESSION_POOL.length < TARGET_USERS) {
  throw new Error(
    `Cookie pool too small for realistic ${TARGET_USERS} users. ` +
      `Current pool: ${SESSION_POOL.length}. Add more cookies or set STRICT_COOKIE_POOL=false.`,
  );
}

function clampWeight(v) {
  return Number.isFinite(v) && v > 0 ? v : 0;
}

const _wErp = clampWeight(ERP_WEIGHT);
const _wChat = clampWeight(CHAT_WEIGHT);
const _wFile = clampWeight(FILE_WEIGHT);
const _wIdle = clampWeight(IDLE_WEIGHT);
const _wSum = _wErp + _wChat + _wFile + _wIdle;

const flowWeights =
  _wSum > 0
    ? {
        erp: _wErp / _wSum,
        chat: _wChat / _wSum,
        file: _wFile / _wSum,
        idle: _wIdle / _wSum,
      }
    : {
        erp: 0.5,
        chat: 0.25,
        file: 0.05,
        idle: 0.2,
      };

export const options = {
  discardResponseBodies: DISCARD_RESPONSE_BODIES,
  // Redirect를 따라가면 (예: /login 302 -> 200) 인증 실패가 숨겨지므로 비활성화
  maxRedirects: 0,
  scenarios: {
    user_sessions: {
      executor: 'ramping-vus',
      startVUs: Math.max(10, Math.floor(TARGET_USERS * 0.2)),
      stages: [
        { duration: '3m', target: TARGET_USERS },
        { duration: TEST_DURATION, target: TARGET_USERS },
        { duration: '2m', target: Math.max(10, Math.floor(TARGET_USERS * 0.3)) },
      ],
      gracefulRampDown: '30s',
      exec: 'userJourney',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<2000'],
    http_req_failed: ['rate<0.05'],
    status_429_rate: ['rate<0.03'],
    status_5xx_rate: ['rate<0.01'],
    status_auth_fail_rate: ['rate<0.02'],
  },
};

function cookieForCurrentVu() {
  const idx = (__VU - 1) % SESSION_POOL.length;
  return SESSION_POOL[idx];
}

function baseAuthHeaders(extraHeaders = {}) {
  return {
    Cookie: `${COOKIE_NAME}=${cookieForCurrentVu()}`,
    ...extraHeaders,
  };
}

function makeParams(extraHeaders = {}, tags = {}) {
  return {
    headers: baseAuthHeaders(extraHeaders),
    tags,
  };
}

function maybeLogError(res, context) {
  if (!TRACE_ERRORS) return;
  if (errorLogCount >= TRACE_MAX_ERROR_LOGS) return;
  if (Math.random() > TRACE_ERROR_SAMPLE_RATE) return;

  errorLogCount += 1;
  let bodySnippet = '';
  if (!DISCARD_RESPONSE_BODIES && typeof res.body === 'string' && res.body.length > 0) {
    bodySnippet = res.body.replace(/\s+/g, ' ').slice(0, 220);
  }
  const locationHeader = (res.headers && (res.headers.Location || res.headers.location)) || '';
  const bodyText = !DISCARD_RESPONSE_BODIES && typeof res.body === 'string' ? res.body : '';
  const isStorageCredentialError =
    context.route === 'chat_upload' &&
    res.status >= 500 &&
    bodyText.indexOf('Credential access key has length') !== -1;

  if (isStorageCredentialError && !storageConfigHintLogged) {
    storageConfigHintLogged = true;
    console.error(
      '[TRACE_HINT] chat_upload 500 is storage credential misconfiguration: ' +
        'R2_ACCESS_KEY_ID length must be 32. Check Railway env vars for R2 key/secret.',
    );
  }

  console.error(
    `[TRACE_ERR] flow=${context.flow} route=${context.route} method=${context.method} status=${res.status} ` +
      `url=${context.url} location=${locationHeader} body="${bodySnippet}"`,
  );
}

function trackStatus(res, context) {
  const locationHeader =
    (res && res.headers && (res.headers.Location || res.headers.location)) || '';
  const redirectedToLogin =
    res.status === 302 &&
    typeof locationHeader === 'string' &&
    locationHeader.indexOf('/login') !== -1;

  const isAuthFail = res.status === 401 || res.status === 403 || redirectedToLogin;
  const isOk = context.okStatuses.includes(res.status);
  const metricTags = {
    flow: context.flow,
    route: context.route,
    method: context.method,
    status: String(res.status),
  };

  requestCount.add(1);
  endpointRequestCount.add(1, metricTags);
  endpointDuration.add(res.timings.duration, metricTags);

  status2xxRate.add(res.status >= 200 && res.status < 300);
  status429Rate.add(res.status === 429);
  status5xxRate.add(res.status >= 500);
  authFailRate.add(isAuthFail);

  if (!isOk) endpointFailCount.add(1, metricTags);
  if (res.status === 429) endpoint429Count.add(1, metricTags);
  if (res.status >= 500) endpoint5xxCount.add(1, metricTags);
  if (isAuthFail) endpointAuthFailCount.add(1, metricTags);

  if (!isOk) maybeLogError(res, context);

  check(res, {
    [`${context.flow}:${context.route} status in ${context.okStatuses.join('/')}`]: () => isOk,
  });
}

function requestWithTrace(method, routePath, flow, routeName, okStatuses = [200], payload = null, extraHeaders = {}) {
  const methodUpper = method.toUpperCase();
  const url = routePath.startsWith('http://') || routePath.startsWith('https://') ? routePath : `${BASE_URL}${routePath}`;
  const params = makeParams(extraHeaders, { flow, route: routeName, method: methodUpper });
  let res;

  if (methodUpper === 'POST') {
    res = http.post(url, payload, params);
  } else if (methodUpper === 'PUT') {
    res = http.put(url, payload, params);
  } else if (methodUpper === 'PATCH') {
    res = http.patch(url, payload, params);
  } else if (methodUpper === 'DELETE') {
    res = http.del(url, null, params);
  } else {
    res = http.get(url, params);
  }

  trackStatus(res, {
    flow,
    route: routeName,
    method: methodUpper,
    url,
    okStatuses,
  });
  return res;
}

function erpFlow() {
  group('erp-flow', () => {
    const page = randomItem(dashboardRoutes);
    requestWithTrace('GET', page.path, 'erp', page.name, [200]);

    const api = randomItem(erpApiRoutes);
    requestWithTrace('GET', api.path, 'erp', api.name, [200]);

    // ERP 화면 체류 시간(문서 확인/입력) 반영
    sleep(Math.random() * 30 + 15);
  });
}

function chatFlow() {
  group('chat-flow', () => {
    requestWithTrace('GET', '/api/chat/rooms', 'chat', 'chat_rooms_list', [200]);

    if (CHAT_ROOM_ID) {
      const payload = JSON.stringify({
        room_id: Number(CHAT_ROOM_ID),
        message_type: 'text',
        content: `load-test message vu=${__VU} iter=${__ITER}`,
      });
      requestWithTrace(
        'POST',
        '/api/chat/messages',
        'chat',
        'chat_send_message',
        [200, 201],
        payload,
        { 'Content-Type': 'application/json' },
      );
    }

    // 채팅은 짧은 왕복이지만 연속 전송은 드묾
    sleep(Math.random() * 17 + 8);
  });
}

function fileFlow() {
  group('file-flow', () => {
    const uploadPayload = {
      file: http.file(uploadBytes, `vu_${__VU}_it_${__ITER}.jpg`, 'image/jpeg'),
      room_id: CHAT_ROOM_ID || '1',
    };
    requestWithTrace('POST', '/api/chat/upload', 'file', 'chat_upload', [200], uploadPayload);

    if (CHAT_DOWNLOAD_KEY) {
      requestWithTrace(
        'GET',
        `/api/chat/download/${CHAT_DOWNLOAD_KEY}`,
        'file',
        'chat_download',
        [200, 302],
      );
    }

    // 파일 업/다운은 간헐적으로 발생
    sleep(Math.random() * 90 + 30);
  });
}

export function userJourney() {
  // 기본 현실형 분포(환경변수로 조정 가능): ERP 50%, 채팅 25%, 파일 5%, 유휴 20%
  const roll = Math.random();
  const erpCut = flowWeights.erp;
  const chatCut = erpCut + flowWeights.chat;
  const fileCut = chatCut + flowWeights.file;

  if (roll < erpCut) {
    erpFlow();
  } else if (roll < chatCut) {
    chatFlow();
  } else if (roll < fileCut) {
    fileFlow();
  } else {
    sleep(Math.random() * 45 + 20);
  }
}

function metricValue(data, metricName, field = 'value', fallback = null) {
  try {
    const metric = data.metrics[metricName];
    if (!metric || !metric.values || metric.values[field] === undefined) return fallback;
    return metric.values[field];
  } catch (e) {
    return fallback;
  }
}

function buildTraceTextSummary(data) {
  const lines = [];
  lines.push('FOMS Load Test Trace Summary');
  lines.push(`target_users=${TARGET_USERS}`);
  lines.push(`duration=${TEST_DURATION}`);
  lines.push(`http_req_failed.rate=${metricValue(data, 'http_req_failed', 'rate', 'n/a')}`);
  lines.push(`status_429_rate.rate=${metricValue(data, 'status_429_rate', 'rate', 'n/a')}`);
  lines.push(`status_5xx_rate.rate=${metricValue(data, 'status_5xx_rate', 'rate', 'n/a')}`);
  lines.push(`status_auth_fail_rate.rate=${metricValue(data, 'status_auth_fail_rate', 'rate', 'n/a')}`);
  lines.push(`http_req_duration.p95=${metricValue(data, 'http_req_duration', 'p(95)', 'n/a')}`);
  lines.push(`endpoint_fail_count.total=${metricValue(data, 'endpoint_fail_count', 'count', 'n/a')}`);
  lines.push(`endpoint_429_count.total=${metricValue(data, 'endpoint_429_count', 'count', 'n/a')}`);
  lines.push(`endpoint_5xx_count.total=${metricValue(data, 'endpoint_5xx_count', 'count', 'n/a')}`);
  lines.push('');
  lines.push('TIP: run with --out json=... for per-request deep trace if needed.');
  return lines.join('\n');
}

export function handleSummary(data) {
  const text = buildTraceTextSummary(data);
  return {
    [TRACE_SUMMARY_JSON]: JSON.stringify(data, null, 2),
    [TRACE_SUMMARY_TXT]: text,
    stdout: text,
  };
}
