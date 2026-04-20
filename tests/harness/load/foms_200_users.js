import http from 'k6/http';
import { check, sleep } from 'k6';

function randomItem(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

const BASE_URL = __ENV.BASE_URL || 'http://localhost:5000';
const COOKIE_NAME = __ENV.COOKIE_NAME || 'session_staging';
const SESSION_COOKIE = __ENV.SESSION_COOKIE || '';

const DASHBOARD_PATHS = [
  '/erp/dashboard',
  '/erp/production/dashboard',
  '/erp/construction/dashboard',
  '/erp/measurement',
  '/erp/shipment',
];

const API_PATHS = [
  '/erp/api/notifications/badge',
  '/api/chat/rooms',
  '/api/orders?limit=500',
];

const uploadBytes = open('./fixtures/upload_sample.txt', 'b');

export const options = {
  discardResponseBodies: true,
  scenarios: {
    mixed_erp_chat: {
      executor: 'ramping-vus',
      startVUs: 20,
      stages: [
        { duration: '2m', target: 80 },
        { duration: '3m', target: 140 },
        { duration: '5m', target: 200 },
        { duration: '2m', target: 50 },
      ],
      gracefulRampDown: '30s',
      exec: 'mixedFlow',
    },
    file_uploads: {
      executor: 'constant-arrival-rate',
      rate: 1,
      timeUnit: '1s',
      duration: '10m',
      preAllocatedVUs: 5,
      maxVUs: 15,
      exec: 'uploadFlow',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.02'],
    http_req_duration: ['p(95)<1500'],
    'http_req_duration{type:upload}': ['p(95)<8000'],
  },
};

function authParams(extraHeaders = {}, tags = {}) {
  const headers = { ...extraHeaders };
  if (SESSION_COOKIE) {
    headers.Cookie = `${COOKIE_NAME}=${SESSION_COOKIE}`;
  }
  return { headers, tags };
}

export function mixedFlow() {
  const dashboardPath = randomItem(DASHBOARD_PATHS);
  const apiPath = randomItem(API_PATHS);

  const dashboardRes = http.get(`${BASE_URL}${dashboardPath}`, authParams({}, { type: 'dashboard' }));
  check(dashboardRes, {
    'dashboard status is 200': (r) => r.status === 200,
  });

  const apiRes = http.get(`${BASE_URL}${apiPath}`, authParams({}, { type: 'api' }));
  check(apiRes, {
    'api status is 200': (r) => r.status === 200,
  });

  sleep(Math.random() * 2 + 0.3);
}

export function uploadFlow() {
  const payload = {
    file: http.file(uploadBytes, `vu_${__VU}_it_${__ITER}.jpg`, 'image/jpeg'),
    room_id: '1',
  };
  const res = http.post(`${BASE_URL}/api/chat/upload`, payload, authParams({}, { type: 'upload' }));
  check(res, {
    'upload status is 200': (r) => r.status === 200,
  });

  sleep(Math.random() * 2 + 1);
}
