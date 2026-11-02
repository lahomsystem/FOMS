/**
 * 회사 지식 '뇌 보기' 순수 함수 — 뇌 바탕 모양 · 키 → 부위 → 자리 · 신경 줄 곡선 · 주름 잡음(설계서 7.6). three.js 없음(node 시험).
 *
 * 좌표: x = 왼쪽 · 오른쪽(s = -1 · +1 반구), y = 위, z = 앞(이마) 쪽. 사장님 시제품(학습 폴더 design/brain3d_prototype —
 * anatomy · layout · noise)을 옮기며 다듬었다: 가운데 공통 바탕 점 뭉침 → 바탕 덩어리를 넓히고 한가운데를 비우고(속이 빈 공 꼴)
 * 유형마다 핵을 고리 위에 떨어뜨려 둔다.
 * 쓰는 곳: brain3d-shell.js(껍데기) · brain3d-scene.js(점 자리). window.FOMS_BRAIN3D_LAYOUT · node module.exports.
 */
(function (root) {
  'use strict';

  var core = root.FOMS_BRAIN3D_CORE || (typeof require === 'function' ? require('./brain3d-core.js') : null);
  var HEMI = { cx: 0.36, rx: 0.48, ry: 0.66, rz: 1.0, gap: 0.016 };

  function clamp(x, a, b) { return x < a ? a : x > b ? b : x; }

  function smoothstep(a, b, x) {
    var t = clamp((x - a) / (b - a), 0, 1);
    return t * t * (3 - 2 * t);
  }

  /** a..b 사이에서 1, 바깥으로 부드럽게 0. */
  function bump(x, a, b, soft) {
    var s = soft === undefined ? 0.15 : soft;
    return smoothstep(a - s, a + s, x) * (1 - smoothstep(b - s, b + s, x));
  }

  function smax(a, b, k) {
    var h = clamp(0.5 + (0.5 * (a - b)) / k, 0, 1);
    return a * h + b * (1 - h) + k * h * (1 - h);
  }

  /** 가쪽 고랑(실비우스) 높이 — 앞 아래에서 뒤 위로. */
  function sylvianY(uz) { return -0.2 + 0.3 * (0.45 - uz); }

  /** 중심 고랑 앞뒤 자리 — 정수리에서 뒤, 아래로 갈수록 앞. */
  function centralZ(uy) { return 0.1 - 0.2 * uy; }

  /** 관자엽 무게(0..1) — 가쪽 아래 · 가쪽 고랑 밑. */
  function temporalWeight(s, ux, uy, uz) {
    return bump(uz, -0.5, 0.42) * smoothstep(0.15, 0.6, ux * s) * smoothstep(0.02, -0.12, uy - sylvianY(uz));
  }

  /** 반구 s 의 단위 방향 u 에 해당하는 겉 껍데기 점(주름 전) — [x, y, z]. */
  function hemiPoint(s, ux, uy, uz) {
    var front = Math.max(uz, 0);
    var back = Math.max(-uz, 0);
    var taper = 1 - 0.22 * front * front - 0.16 * back * back;
    var crown = 1 - 0.18 * front * front - 0.3 * back * back * back;
    var tw = temporalWeight(s, ux, uy, uz);
    var x = s * HEMI.cx + ux * HEMI.rx * taper;
    var y = uy * HEMI.ry * (uy > 0 ? crown : 1);
    var z = uz * HEMI.rz * (1 - 0.04 * tw);
    y -= 0.12 * tw;  // 관자엽 — 아래 · 바깥으로 불룩
    x += s * 0.05 * tw;
    var floor = -0.3 + 0.2 * smoothstep(-0.35, -0.95, uz) - 0.14 * tw;  // 밑면 — 뒤로 갈수록 올라간다(소뇌 위 천막)
    var press = smoothstep(floor + 0.06, floor - 0.06, y);
    y += (floor + (y - floor) * 0.3 - y) * press;
    x = s * smax(s * x, HEMI.gap, 0.035);  // 안쪽 벽 — 두 반구 사이 세로 틈
    return [x, y, z];
  }

  /** 큰 고랑 무게(0..1): 가쪽 고랑 · 중심 고랑 — 껍데기가 이 자리를 깊게 판다. */
  function fissureWeight(s, ux, uy, uz) {
    var dy = uy - sylvianY(uz);
    var sylvian = Math.exp(-Math.pow(dy / 0.05, 2)) * smoothstep(0.3, 0.65, ux * s) * bump(uz, -0.42, 0.48, 0.08);
    var dz = uz - centralZ(uy);
    var central = Math.exp(-Math.pow(dz / 0.035, 2)) * smoothstep(0.0, 0.12, dy) * smoothstep(-0.35, -0.1, ux * s);
    return Math.max(sylvian, central * 0.85);
  }

  function randomDir(rnd) {
    var z = 2 * rnd() - 1;
    var phi = 2 * Math.PI * rnd();
    var r = Math.sqrt(1 - z * z);
    return [r * Math.cos(phi), r * Math.sin(phi), z];
  }

  // 겉(피질) 부위 — 방향 공간 조건. s = 반구(±1), u = 반구 가운데에서 본 방향.
  var CORTEX = {
    frontal: function (s, u) { return u[2] > 0.38 && u[1] > sylvianY(u[2]) + 0.02 && u[2] > centralZ(u[1]) + 0.2; },
    temporal: function (s, u) { return temporalWeight(s, u[0], u[1], u[2]) > 0.55 && u[0] * s > 0.4; },
    occipital: function (s, u) { return u[2] < -0.66 && u[1] > -0.55; },
    motor: function (s, u) {
      var dz = u[2] - centralZ(u[1]);
      return dz > 0.035 && dz < 0.12 && u[1] > sylvianY(u[2]) + 0.1 && u[0] * s > -0.25;
    }
  };
  var CORTEX_DEPTH = [0.84, 0.95];  // 피질 바로 밑(반구 가운데 → 겉 비율)
  // 가운데 깊은 곳 — 시제품보다 넓힌 타원 덩어리, 한가운데 40% 는 비운다(점 뭉침 줄이기)
  var BASE = { c: [0, -0.06, 0.03], r: [0.36, 0.25, 0.52], hollow: 0.4 };
  var TYPE_PULL = 0.32;

  function sampleCortex(region, rnd, side) {
    var s = side || (rnd() < 0.5 ? -1 : 1);
    var u = randomDir(rnd);
    for (var i = 0; i < 2000 && !CORTEX[region](s, u); i++) u = randomDir(rnd);
    return { s: s, u: u };
  }

  function cortexPoint(s, u, depth) {
    var p = hemiPoint(s, u[0], u[1], u[2]);
    var cx = s * HEMI.cx;
    return [cx + (p[0] - cx) * depth, p[1] * depth, p[2] * depth];
  }

  function basePoint(rnd, inner) {
    var d = randomDir(rnd);
    var low = Math.pow(inner === undefined ? BASE.hollow : inner, 3);
    var r = Math.cbrt(low + (1 - low) * rnd());
    return [BASE.c[0] + d[0] * r * BASE.r[0], BASE.c[1] + d[1] * r * BASE.r[1], BASE.c[2] + d[2] * r * BASE.r[2]];
  }

  // 해마 — 관자엽 안쪽을 따라 앞에서 뒤로 휘는 관(양쪽)
  function hippoPoint(rnd) {
    var s = rnd() < 0.5 ? -1 : 1;
    var t = rnd();
    var a = [s * 0.3, -0.3, 0.16];
    var b = [s * 0.32, -0.24, -0.42];
    var c = [s * 0.1, 0.06, -0.4];
    var k = [(1 - t) * (1 - t), 2 * (1 - t) * t, t * t];
    var d = randomDir(rnd);
    var rad = 0.05 * (1 - 0.45 * t) * Math.cbrt(rnd());
    return [0, 1, 2].map(function (i) { return k[0] * a[i] + k[1] * b[i] + k[2] * c[i] + d[i] * rad; });
  }

  function lerp3(a, b, k) { return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k]; }

  function normalize(v) {
    var l = Math.hypot(v[0], v[1], v[2]) || 1;
    return [v[0] / l, v[1] / l, v[2] / l];
  }

  var anchors = {};

  /** 유형마다 부위 안 작은 핵(유형 이름 해시) — 같은 유형이 조금 모인다. 바탕 핵은 바깥 껍질 쪽에 둔다. */
  function typeAnchor(region, type, side) {
    var id = type + ':' + side;
    if (!anchors[id]) {
      var rnd = core.randomForKey('anchor:' + id);
      anchors[id] = CORTEX[region] ? sampleCortex(region, rnd, side) : { p: region === 'base' ? basePoint(rnd, 0.75) : hippoPoint(rnd) };
    }
    return anchors[id];
  }

  /** 항목 하나의 자리 — 같은 키 · 유형 · 층이면 늘 같은 [x, y, z]. */
  function positionFor(item) {
    var region = item.region || core.regionOf(item.type, item.layer);
    var rnd = core.randomForKey(item.key);
    if (CORTEX[region]) {
      var c = sampleCortex(region, rnd);
      var u = normalize(lerp3(c.u, typeAnchor(region, item.type, c.s).u, TYPE_PULL));
      return cortexPoint(c.s, u, CORTEX_DEPTH[0] + (CORTEX_DEPTH[1] - CORTEX_DEPTH[0]) * rnd());
    }
    if (region === 'hippo') return hippoPoint(rnd);  // 관은 가늘어 핵으로 당기지 않는다
    return lerp3(basePoint(rnd), typeAnchor('base', item.type, 0).p, TYPE_PULL * 0.6);
  }

  /** 모든 항목의 자리 — Float32Array(x, y, z 차례). */
  function layoutAll(items) {
    var out = new Float32Array(items.length * 3);
    items.forEach(function (it, i) {
      var p = positionFor(it);
      out[i * 3] = p[0];
      out[i * 3 + 1] = p[1];
      out[i * 3 + 2] = p[2];
    });
    return out;
  }

  var BEND_TO = [0, -0.04, 0];
  var BEND = 0.32;

  /** 신경 줄 곡선 — 가운데(흰질) 쪽으로 휘는 2차 곡선 위 t(0..1) 자리를 out 에. 줄 · 빛 흐름이 같은 식. */
  function curvePoint(pos, a, b, t, out) {
    var o = out || [0, 0, 0];
    for (var i = 0; i < 3; i++) {
      var pa = pos[a * 3 + i];
      var pb = pos[b * 3 + i];
      var mid = (pa + pb) / 2;
      var m = mid + (BEND_TO[i] - mid) * BEND;
      o[i] = (1 - t) * (1 - t) * pa + 2 * (1 - t) * t * m + t * t * pb;
    }
    return o;
  }

  // 주름 잡음 — 3D 경사 잡음(Perlin 꼴). 씨앗이 고정이라 껍데기 주름이 늘 같다.
  var perm = new Uint8Array(512);
  (function init() {
    var rnd = core.seededRandom(7);
    var p = [];
    for (var i = 0; i < 256; i++) p.push(i);
    for (var j = 255; j > 0; j--) {
      var k = Math.floor(rnd() * (j + 1));
      var tmp = p[j]; p[j] = p[k]; p[k] = tmp;
    }
    for (var n = 0; n < 512; n++) perm[n] = p[n & 255];
  })();
  var GRAD = [[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0], [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1],
              [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1]];

  function fade(t) { return t * t * t * (t * (t * 6 - 15) + 10); }
  function grad(h, x, y, z) { var g = GRAD[h % 12]; return g[0] * x + g[1] * y + g[2] * z; }
  function mix(a, b, t) { return a + t * (b - a); }

  /** 대략 -1..1 사이 잡음 값. */
  function noise3(x, y, z) {
    var X = Math.floor(x) & 255, Y = Math.floor(y) & 255, Z = Math.floor(z) & 255;
    x -= Math.floor(x); y -= Math.floor(y); z -= Math.floor(z);
    var u = fade(x), v = fade(y), w = fade(z);
    var A = perm[X] + Y, AA = perm[A] + Z, AB = perm[A + 1] + Z;
    var B = perm[X + 1] + Y, BA = perm[B] + Z, BB = perm[B + 1] + Z;
    return mix(
      mix(mix(grad(perm[AA], x, y, z), grad(perm[BA], x - 1, y, z), u),
          mix(grad(perm[AB], x, y - 1, z), grad(perm[BB], x - 1, y - 1, z), u), v),
      mix(mix(grad(perm[AA + 1], x, y, z - 1), grad(perm[BA + 1], x - 1, y, z - 1), u),
          mix(grad(perm[AB + 1], x, y - 1, z - 1), grad(perm[BB + 1], x - 1, y - 1, z - 1), u), v), w);
  }

  var api = {
    HEMI: HEMI, clamp: clamp, smoothstep: smoothstep, bump: bump, sylvianY: sylvianY, centralZ: centralZ,
    temporalWeight: temporalWeight, hemiPoint: hemiPoint, fissureWeight: fissureWeight, positionFor: positionFor,
    layoutAll: layoutAll, curvePoint: curvePoint, noise3: noise3, BASE: BASE
  };
  root.FOMS_BRAIN3D_LAYOUT = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
