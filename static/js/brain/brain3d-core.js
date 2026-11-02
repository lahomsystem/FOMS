/**
 * 회사 지식 '뇌 보기' 순수 함수(HAUD master brain 설계서 7.6 · 사장님 D100) — three.js 를 쓰지 않는다(node 시험).
 *
 * - 키 해시(FNV-1a) · 씨앗 난수(mulberry32): 같은 키면 늘 같은 자리(물리 배치 없음 — 새로 열어도 같다).
 * - 층 · 유형 → 뇌 부위(7.6 표): 공통 바탕 = 가운데 깊은 곳 · 결정 · 정책 · 가격 = 이마엽 · 상담 층 = 관자엽 · 도면 층 = 뒤통수엽 ·
 *   생산 층 = 운동 피질 띠 · 관찰 = 해마 자리 · 에이전트 일(엇갈림 · 물어볼 것) = 이마엽(D100).
 * - 색: 유형 색은 화면 표시 표(display.py — 모든 화면 같은 색)를 어두운 바탕용으로 밝힌 것. 낡음 = 주황, 은퇴 = 회색, 초안 = 흐린 테.
 *   밝기 = 쓰인 횟수(log 눈금 — 지금은 모두 0).
 * - 그래픽 판별: 휴대폰 · WebGL 없음 · 소프트웨어 그리기(SwiftShader · llvmpipe · 'Software' …)면 탭을 숨긴다.
 * window.FOMS_BRAIN3D_CORE 로 내놓고 node 에서는 module.exports — tests/domains/test_brain3d_js.py.
 */
(function (root) {
  'use strict';

  /** FNV-1a 32비트 해시 — 같은 글이면 늘 같은 수. */
  function hashKey(text) {
    var h = 0x811c9dc5;
    var s = String(text || '');
    for (var i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 0x01000193);
    }
    return h >>> 0;
  }

  /** mulberry32 — 씨앗 하나로 0 이상 1 미만 수를 차례로 낸다. */
  function seededRandom(seed) {
    var a = seed >>> 0;
    return function next() {
      a = (a + 0x6d2b79f5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function randomForKey(key) {
    return seededRandom(hashKey(key));
  }

  /** 뇌 부위 — 이름 · 층 · 까닭(7.6 표). 차례 = 범례 차례. */
  var REGIONS = [
    { code: 'base', name: '가운데 깊은 곳', layer: '공통 바탕(제품 · 규격 · 제작 조건 · 용어)', why: '모든 팀이 기대는 바탕' },
    { code: 'frontal', name: '앞쪽(이마엽)', layer: '사장님 결정 · 정책 · 가격 규칙 · 에이전트 일', why: '판단 · 규칙' },
    { code: 'temporal', name: '옆쪽(관자엽)', layer: '상담 층', why: '말 · 언어' },
    { code: 'occipital', name: '뒤쪽(뒤통수엽)', layer: '도면 층', why: '보기 · 그림' },
    { code: 'motor', name: '정수리 띠(운동 피질)', layer: '생산 층(판 3)', why: '손 · 만들기' },
    { code: 'hippo', name: '안쪽 해마 자리', layer: '관찰 · 사례', why: '기억' }
  ];

  var TYPE_REGION = {
    brand: 'base', product_line: 'base', option: 'base', spec: 'base', build_rule: 'base', term: 'base', fact: 'base',
    policy: 'frontal', price_rule: 'frontal', owner_decision: 'frontal', conflict: 'frontal', question: 'frontal',
    situation: 'temporal', template: 'temporal', lesson: 'temporal', tone: 'temporal', image_read_rule: 'temporal',
    part_kind: 'occipital', bom_rule: 'occipital', drawing_rule: 'occipital',
    case: 'hippo', image_read: 'hippo', photo_observation: 'hippo'
  };
  var LAYER_REGION = { common: 'base', cs: 'temporal', drawing: 'occipital', production: 'motor' };

  /** 유형(먼저) · 층 → 부위 코드. 관찰 · 에이전트 일은 어느 층이든 유형대로. */
  function regionOf(type, layer) {
    return TYPE_REGION[type] || LAYER_REGION[layer] || 'base';
  }

  var FLAG_DRAFT = 1;
  var FLAG_RETIRED = 2;
  var FLAG_STALE = 4;
  var STALE = '#fb923c';  // brain.css --brain-stale 계열(어두운 바탕용으로 밝힘)
  var RETIRED = '#9ca3af';  // brain.css --brain-retired
  var FALLBACK = '#94a3b8';

  /** '#rrggbb' → [r, g, b](0..1). 틀리면 회청색. */
  function hexRgb(hex) {
    var m = /^#?([0-9a-f]{6})$/i.exec(String(hex || ''));
    var n = parseInt(m ? m[1] : FALLBACK.slice(1), 16);
    return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
  }

  /** 흰색 쪽으로 섞기 — 화면 표의 진한 유형 색을 어두운 3D 바탕에서 보이게(같은 색 계열 유지). */
  function lighten(rgb, amount) {
    var k = Math.max(0, Math.min(1, Number(amount) || 0));
    return [rgb[0] + (1 - rgb[0]) * k, rgb[1] + (1 - rgb[1]) * k, rgb[2] + (1 - rgb[2]) * k];
  }

  /** 상태 표시 비트(초안 · 은퇴 · 낡음) — 항목 줄(status · stale)에서. */
  function flagsOf(item) {
    var f = 0;
    if (item && item.status === 'draft') f |= FLAG_DRAFT;
    if (item && item.status === 'retired') f |= FLAG_RETIRED;
    if (item && item.stale) f |= FLAG_STALE;
    return f;
  }

  /** 점 색 — 은퇴 회색 > 낡음 주황 > 유형 색(밝힌 것). */
  function pointColor(type, flags, display) {
    if (flags & FLAG_RETIRED) return hexRgb(RETIRED);
    if (flags & FLAG_STALE) return hexRgb(STALE);
    var t = display && display.types && display.types[type];
    return lighten(hexRgb(t ? t.color : FALLBACK), 0.42);
  }

  /** 링크 종류 색(밝힌 것) — 고른 항목의 신경 줄 · 빛 흐름. */
  function linkColor(kind, display) {
    var l = display && display.links && display.links[kind];
    return lighten(hexRgb(l ? l.color : FALLBACK), 0.35);
  }

  /** 밝기 0..1 — 쓰인 횟수 log 눈금(가장 많이 쓰인 항목 = 1). 은퇴는 늘 흐리게. */
  function glow(usage, maxUsage, flags) {
    if (flags & FLAG_RETIRED) return 0.1;
    var top = Math.max(1, Number(maxUsage) || 0);
    return Math.log1p(Math.max(0, Number(usage) || 0)) / Math.log1p(top);
  }

  /** /api/brain/points 답 → [{key, type, flags, usage}](모르는 유형 번호는 빈 유형). */
  function decodePoints(data) {
    var types = (data && data.types) || [];
    return ((data && data.rows) || []).map(function (row) {
      return { key: String(row[0]), type: types[row[1]] || '', flags: Number(row[2]) || 0, usage: Number(row[3]) || 0 };
    });
  }

  var SOFTWARE = /swiftshader|llvmpipe|softpipe|lavapipe|software|basic render|mesa offscreen/i;

  /** WebGL 그리는 이 이름이 소프트웨어 그리기인가(설계서 7.6 '그래픽 없는 기기 판별' — 6~11 FPS 라 숨김). */
  function isSoftwareRenderer(name) {
    return SOFTWARE.test(String(name || ''));
  }

  /** 휴대폰인가 — 좁은 화면(768px 미만) 또는 거친 포인터 + 가리키기 없음(손가락 기기). */
  function isPhone(env) {
    var e = env || {};
    return Number(e.width) > 0 && Number(e.width) < 768 || (!!e.coarse && !e.hover);
  }

  /** 탭을 보일지 — {show, reason}(reason: 'phone' · 'no_webgl' · 'software' · null). */
  function canShow3d(env) {
    var e = env || {};
    if (isPhone(e)) return { show: false, reason: 'phone' };
    if (!e.webgl) return { show: false, reason: 'no_webgl' };
    if (isSoftwareRenderer(e.renderer)) return { show: false, reason: 'software' };
    return { show: true, reason: null };
  }

  var api = {
    hashKey: hashKey, seededRandom: seededRandom, randomForKey: randomForKey, REGIONS: REGIONS, regionOf: regionOf,
    FLAG_DRAFT: FLAG_DRAFT, FLAG_RETIRED: FLAG_RETIRED, FLAG_STALE: FLAG_STALE, hexRgb: hexRgb, lighten: lighten,
    flagsOf: flagsOf, pointColor: pointColor, linkColor: linkColor, glow: glow, decodePoints: decodePoints,
    isSoftwareRenderer: isSoftwareRenderer, isPhone: isPhone, canShow3d: canShow3d
  };
  root.FOMS_BRAIN3D_CORE = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
