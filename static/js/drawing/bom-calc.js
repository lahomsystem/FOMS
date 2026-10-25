/**
 * 도면 마법사 — 자재표 계산(순수 계산, 화면을 건드리지 않는다).
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.3 · §3.6
 * - 식은 지난 자재표 670장에서 가장 많이 쓴 값을 찾은 초안이다(도면팀 확인 전).
 *   식에 들어가는 숫자(rules)는 서버 설정(/api/orders/drawing-wizard/bom-rules)에서 받는다.
 * - 옆벽 SR 은 넣은 값을 그대로 적는다. 보조목·EP 41 띠·주방 문 높이는 규칙을 못 찾아 계산하지 않는다.
 * - 시트에 사람이 친 자재표 글자를 읽어 계산과 줄마다 맞춰 본다(같음·여유·짧음·다름·아직 안 침).
 * - 근거 글의 숫자에는 규칙 이름을 붙인다('(1000 − 쌍문 틈 34) ÷ 2 내림' — 보고서 2026-10-25 보통-3).
 *
 * window.FomsBomCalc = { LINES, LINE_NAMES, HANDLES, NOMOLD, sanitize, emptyInputs, calc, toText,
 *                        parseBom, compare, guessLine, guessHandle, parseSpec }
 *   inputs : { line, handle, nomold, W, D, H, zone, door_h, ep, sr_l, sr_r, mods: [{ w, doors, drawers, rods }] }
 *            (서버 calc.in 과 같은 칸 — foms/api/drawing/wizard.py _CALC_CHOICES · _CALC_NUMBERS)
 */
(function () {
  'use strict';
  if (window.FomsBomCalc) { return; }

  var LINES = ['mold', 'nomold', 'slide', 'other'];
  var LINE_NAMES = { mold: '몰딩 여닫이', nomold: '무몰딩 여닫이', slide: '슬라이딩', other: '냉장고장·그 밖' };
  var HANDLES = ['phoenix', 'other'];
  var NOMOLD = ['ceiling', 'std'];
  var NUMBERS = { W: 20000, D: 2000, H: 5000, zone: 3000, door_h: 5000, ep: 4, sr_l: 1000, sr_r: 1000 };
  var MOD_NUMBERS = { w: 5000, doors: 4, drawers: 6, rods: 3 };
  var MAX_MODS = 24, MAX_OUT = 2000, MAX_BYTES = 4000;
  var RULES_RE = /^[A-Za-z0-9._-]{1,16}$/;

  function pick(v, list, def) { return list.indexOf(v) >= 0 ? v : def; }
  function int(v, hi) {
    var n = Math.round(Number(v));
    return isFinite(n) ? Math.max(0, Math.min(hi, n)) : 0;
  }
  function bytes(o) {
    var s = JSON.stringify(o);
    return typeof TextEncoder === 'function' ? new TextEncoder().encode(s).length : s.length * 3;
  }

  /** 저장 직전 정리 — 서버 검증을 늘 통과하는 꼴로만 돌려준다(아니면 null). */
  function sanitize(c) {
    if (!c || typeof c !== 'object') { return null; }
    var src = (c.in && typeof c.in === 'object') ? c.in : {};
    var inp = {
      line: pick(src.line, LINES, 'mold'), handle: pick(src.handle, HANDLES, 'other'), nomold: pick(src.nomold, NOMOLD, 'ceiling')
    };
    Object.keys(NUMBERS).forEach(function (k) { inp[k] = int(src[k], NUMBERS[k]); });
    inp.mods = (Array.isArray(src.mods) ? src.mods : []).slice(0, MAX_MODS).map(function (m) {
      var out = {};
      Object.keys(MOD_NUMBERS).forEach(function (k) { out[k] = int(m && m[k], MOD_NUMBERS[k]); });
      return out;
    });
    var res = { in: inp, mode: c.mode === 'insert' ? 'insert' : 'shadow' };
    if (typeof c.rules === 'string' && RULES_RE.test(c.rules)) { res.rules = c.rules; }
    if (typeof c.out === 'string') { res.out = c.out.slice(0, MAX_OUT); }
    if (bytes(res) > MAX_BYTES) { delete res.out; }   // 계산 글자는 입력값으로 다시 만들 수 있다
    return res;
  }

  /** 제품 규격 'W×D×H' 글자에서 폭·깊이·높이. 못 읽으면 null. */
  function parseSpec(spec) {
    var m = /(\d{3,5})\s*[×xX*]\s*(\d{2,4})\s*[×xX*]\s*(\d{3,4})/.exec(String(spec || ''));
    return m ? { W: +m[1], D: +m[2], H: +m[3] } : null;
  }
  function guessLine(name) {
    var n = String(name || '');
    if (/슬라이딩/.test(n)) { return 'slide'; }
    if (/무몰딩/.test(n)) { return 'nomold'; }
    if (/몰딩/.test(n)) { return 'mold'; }
    if (/냉장고|주방|싱크|키큰/.test(n)) { return 'other'; }
    return 'mold';
  }
  function guessHandle(name) { return /피닉스/.test(String(name || '')) ? 'phoenix' : 'other'; }

  /** 제품(이름·규격)으로 미리 채운 입력값. 모듈은 비워 둔다. */
  function emptyInputs(rules, product) {
    var p = product || {};
    var wdh = parseSpec(p.spec) || { W: 0, D: 0, H: 0 };
    return {
      line: guessLine(p.name), handle: guessHandle(p.name), nomold: 'ceiling',
      W: wdh.W, D: wdh.D, H: wdh.H, zone: (rules && rules.drawer_zone) || 0, door_h: 0, ep: 0, sr_l: 0, sr_r: 0, mods: []
    };
  }

  /* ---- 계산식 ---- */
  // 근거 글에 붙이는 규칙 이름(규칙 창 칸 이름을 줄인 것). 숫자만 있으면 무슨 규칙인지 모른다.
  var RULE_NAMES = {
    door_gap_phoenix_pair: '쌍문 틈', door_gap_other_pair: '쌍문 틈', door_gap_phoenix_single: '외짝 틈',
    door_gap_other_single: '외짝 틈', door_ceiling_margin: '띄울 높이', nomold_cut: '무몰딩 빼기',
    rod_cut: '옷봉 빼기', maida_w_cut: '폭 빼기', maida_h_cut: '높이 빼기', sr_small_gap: '작은 틈 기준',
    sr_minus: '틈 빼기', sheet_len: '판 길이', ep_plus_hinged: '여닫이 더하기'
  };
  function rn(r, key) { return RULE_NAMES[key] + ' ' + r[key]; }

  function doorHeight(s, r) {
    if (s.door_h > 0) { return { h: s.door_h, why: '직접 넣은 값' }; }
    if (s.line === 'nomold' && s.nomold === 'ceiling') {
      return { h: Math.floor((s.H - r.nomold_cut) / r.nomold_step) * r.nomold_step,
        why: '천장 ' + s.H + ' − ' + rn(r, 'nomold_cut') + ' → ' + r.nomold_step + ' 단위 내림' };
    }
    var std = r.door_std_heights;
    var ok = std.filter(function (h) { return h <= s.H - r.door_ceiling_margin; });
    return { h: ok.length ? ok[ok.length - 1] : std[0],
      why: '표준 문 중 천장 ' + s.H + ' − ' + rn(r, 'door_ceiling_margin') + ' 이하에서 가장 큰 것' + (s.line === 'other' ? '(냉장고장·그 밖은 추정)' : '') };
  }
  function doorWidth(w, n, s, r) {
    if (s.line === 'slide') { return { w: w, why: '슬라이딩 문 = 모듈 폭 ' + w }; }
    var key = 'door_gap_' + (s.handle === 'phoenix' ? 'phoenix' : 'other') + (n === 1 ? '_single' : '_pair');
    if (n === 1) { return { w: w - r[key], why: w + ' − ' + rn(r, key) }; }
    return { w: Math.floor((w - r[key]) / n), why: '(' + w + ' − ' + rn(r, key) + ') ÷ ' + n + ' 내림' };
  }
  function add(map, a, b, qty, why) {
    var key = b == null ? String(a) : a + '*' + b;
    if (!map[key]) { map[key] = { a: a, b: b, q: 0, why: why }; }
    map[key].q += qty;
  }

  /** 입력값 + 규칙 숫자 → 줄 목록 [{head}] · [{sec, text, a, b, q, why, ea?}]. */
  function calc(s, r) {
    if (!s || !r) { return []; }
    var hasH = s.H > 0 || s.door_h > 0;
    var dh = hasH ? doorHeight(s, r) : null;
    var zone = s.zone > 0 ? s.zone : r.drawer_zone;
    var door = {}, rod = {}, maida = {}, sr = {}, ep = {};
    (s.mods || []).forEach(function (m) {
      if (!(m.w > 0)) { return; }
      if (m.doors > 0 && dh) {
        var dw = doorWidth(m.w, s.line === 'slide' ? 1 : m.doors, s, r);
        var withDrawer = m.drawers > 0 && s.line !== 'slide';
        add(door, dw.w, withDrawer ? dh.h - zone : dh.h, m.doors,
          dw.why + (withDrawer ? ' · 높이 ' + dh.h + ' − 서랍 칸 ' + zone : ' · 높이: ' + dh.why));
      }
      if (m.drawers > 0) {
        add(maida, m.w - r.maida_w_cut, Math.round(zone / m.drawers - r.maida_h_cut), m.drawers,
          '(' + m.w + ' − ' + rn(r, 'maida_w_cut') + ') × (' + zone + ' ÷ ' + m.drawers + ' − ' + rn(r, 'maida_h_cut') + ')');
      }
      if (m.rods > 0) { add(rod, m.w - r.rod_cut, null, m.rods, m.w + ' − ' + rn(r, 'rod_cut')); }
    });
    if (dh && s.H > 0 && s.W > 0 && s.H - dh.h > 0) {
      var gap = s.H - dh.h, q = Math.ceil(s.W / r.sheet_len);
      var small = gap <= r.sr_small_gap;
      var top = small ? r.sr_small_value : Math.ceil((gap - r.sr_minus) / r.sr_step) * r.sr_step;
      add(sr, top, r.sheet_len, q, (small ? '위 틈 ' + gap + '(' + rn(r, 'sr_small_gap') + ' 이하) → ' + top
        : '위 틈 ' + gap + ' − ' + rn(r, 'sr_minus') + ' → ' + r.sr_step + ' 단위 올림') + ' · 폭 ' + s.W + ' ÷ ' + rn(r, 'sheet_len') + ' 올림 ' + q + '장');
    }
    [s.sr_l, s.sr_r].forEach(function (g) { if (g > 0) { add(sr, g, r.sheet_len, 1, '옆벽 SR(넣은 값)'); } });
    if (s.ep > 0 && s.D > 0) {
      var plus = (s.line === 'mold' || s.line === 'nomold') ? r.ep_plus_hinged : 0;
      add(ep, s.D + plus, r.sheet_len, s.ep, '깊이 ' + s.D + (plus ? ' + ' + rn(r, 'ep_plus_hinged') : ' 그대로') + ' · ' + rn(r, 'sheet_len'));
    }
    var out = [];
    function push(head, map, sorter) {
      var rows = Object.keys(map).map(function (k) { return map[k]; });
      if (!rows.length) { return; }
      out.push({ head: head });
      rows.sort(sorter).forEach(function (e) {
        var item = { sec: head, text: (e.b == null ? e.a : e.a + '*' + e.b) + '=' + e.q, a: e.a, b: e.b, q: e.q, why: e.why };
        if (head === 'DOOR' && s.handle === 'phoenix') { item.ea = Math.ceil(e.q / 2); }
        out.push(item);
      });
    }
    push('SR', sr, function (x, y) { return x.a - y.a; });
    push('EP', ep, function (x, y) { return x.a - y.a; });
    push('DOOR', door, function (x, y) { return (y.b - x.b) || (y.a - x.a); });
    push('옷봉', rod, function (x, y) { return y.a - x.a; });
    push('마이다', maida, function (x, y) { return (y.a - x.a) || (y.b - x.b); });
    return out;
  }

  function toText(lines) {
    var t = [];
    (lines || []).forEach(function (l) {
      if (l.head) { t.push('[' + l.head + ']'); return; }
      t.push(l.text);
      if (l.ea) { t.push('ㄴ피닉스바 ' + l.ea + 'EA'); }
    });
    return t.join('\n');
  }

  /* ---- 시트에 친 자재표 읽기·맞춰 보기 ---- */
  var ALIAS = { SR: 'SR', '스라': 'SR', EP: 'EP', DOOR: 'DOOR', '도어': 'DOOR', '옷봉': '옷봉', '마이다': '마이다' };

  /** 글자 객체 하나씩 → [{sec, a, b, q, ea?, bojo?, text}]. 머리글 없이 친 크기 줄은 버리고
      그 수를 rows.orphans 에 둔다(계산 칸이 '머리글과 한 상자에 써 달라'고 알린다). */
  function parseBom(texts) {
    var rows = [];
    rows.orphans = 0;
    (texts || []).forEach(function (text) {
      var cur = null;
      String(text || '').split(/\r?\n/).forEach(function (raw) {
        var line = raw.replace(/＊|×/g, '*').replace(/＝/g, '=').trim();
        if (!line) { return; }
        var h = /^\[\s*([^\]]+?)\s*\]/.exec(line);
        if (h) {   // '[SR] 60*2440=2' 처럼 머리글 뒤에 바로 쓴 줄도 읽는다
          var w = h[1].replace(/\s+/g, '');
          cur = ALIAS[w.toUpperCase()] || ALIAS[w] || ('기타 ' + w);
          line = line.slice(h[0].length).trim();
          if (!line) { return; }
        }
        if (!cur) {
          if (/^\d{2,4}\s*([*xX+]\s*\d{2,4}\s*)?[=:]\s*\d{1,3}/.test(line)) { rows.orphans += 1; }
          return;
        }
        var bj = /보조목\s*[=:]?\s*(\d{1,3})/.exec(line);
        if (bj) { rows.push({ sec: cur, bojo: true, q: +bj[1], text: line }); return; }
        if (/^(ㄴ|L)/.test(line)) {
          var e = /(\d{1,2})\s*EA/i.exec(line), last = rows[rows.length - 1];
          if (e && last && !last.bojo) { last.ea = (last.ea || 0) + (+e[1]); }
          return;
        }
        var m = /^(\d{2,4})\s*[*xX+]\s*(\d{2,4})\s*[=:]\s*(\d{1,3})/.exec(line);
        if (m) { rows.push({ sec: cur, a: +m[1], b: +m[2], q: +m[3], text: line }); return; }
        var o = /^(\d{2,4})\s*[=:]\s*(\d{1,3})/.exec(line);
        if (o) { rows.push({ sec: cur, a: +o[1], b: null, q: +o[2], text: line }); }
      });
    });
    return rows;
  }

  /* 짝짓기 시험 — 짝이면 {d: 차이 크기, kind?, note?}. 같은 차례 안에서는 차이가 작은 짝부터 정한다. */
  function exact(r, l) { return (r.a === l.a && r.b === l.b) ? { d: r.q === l.q ? 0 : 0.5 } : null; }   // 수량까지 같은 줄 먼저
  /** 한 치수는 같고 다른 치수가 ±20 안 — '여유 +13(시트 496*2160=1)'. 수량까지 다르면 빨강으로 '수량 다름'도 적는다. */
  function nearMiss(r, l) {
    var da = r.a - l.a, db = (r.b == null || l.b == null) ? 0 : r.b - l.b;
    var d = (da === 0) ? db : (db === 0 ? da : 0);
    if (!d || d > 20 || d < -20) { return null; }
    var qty = r.q === l.q ? '' : ' · 수량 다름';
    return { d: Math.abs(d), kind: (d > 0 && !qty) ? 'warn' : 'bad',
      note: (d > 0 ? '여유 +' : '짧음 ') + d + qty + '(시트 ' + r.text + ')' };
  }
  function nearSameQty(r, l) { return r.q === l.q ? nearMiss(r, l) : null; }
  function nearOtherQty(r, l) { return r.q !== l.q ? nearMiss(r, l) : null; }
  var DIMS = { SR: ['폭', '길이'], EP: ['폭', '길이'], '옷봉': ['길이'] };   // 그 밖(DOOR·마이다)은 너비·높이
  // 한 치수 차이 한도 — 넘으면 다른 물건이라 두 줄(시트에 없음·계산에 없음)로 가른다. 문 높이만 표준 높이 두 칸(200)까지
  // (실화면 QA 2026-10-25: 옷봉 465 ↔ 시트 1200 이 '길이 -735', 문 470 ↔ 시트 900 이 '너비 -430' 한 줄로 묶였다).
  var ONE_DIM_MAX = 100, DOOR_H_MAX = 200;
  /** 수량이 같고 한 치수만 다른 줄 — 두 줄로 가르지 않고 '높이 +100(시트 2260)' 한 줄로. 차이는 여유·짧음과 같은 방향
      (시트 − 계산, 시트가 크면 +) — 한 칸 안에 '높이 -100(시트 2260)'·'여유 +10(시트 975=4)'이 섞였다(실화면 QA). */
  function oneDim(r, l) {
    if (r.q !== l.q) { return null; }
    var names = DIMS[l.sec] || ['너비', '높이'];
    var i = (r.a === l.a && r.b != null && l.b != null && r.b !== l.b) ? 1 : ((r.a !== l.a && r.b === l.b) ? 0 : -1);
    if (i < 0) { return null; }
    var mine = i ? l.b : l.a, theirs = i ? r.b : r.a, d = theirs - mine;
    if (Math.abs(d) > (l.sec === 'DOOR' && i ? DOOR_H_MAX : ONE_DIM_MAX)) { return null; }
    return { d: Math.abs(d), kind: 'bad', note: names[i] + ' ' + (d > 0 ? '+' : '') + d + '(시트 ' + theirs + ')' };
  }

  /** 계산 줄 ↔ 시트 줄 → [{sec, text, kind: ok|warn|bad|todo|extra, note}].
      짝짓는 차례: 꼭 맞는 줄 → 수량 같고 ±20 안 → 수량 같고 한 치수만 다름(±100, 문 높이 ±200) → 수량 다르고 ±20 안.
      차례를 나눠야 더 나은 짝을 덜 맞는 짝이 먼저 가져가지 않는다(실화면 QA 2026-10-25: 수량을 안 보는 ±20 짝이
      높이만 다른 같은 문 '483*2160=6 ↔ 시트 483*2260=6'을 갈라 놓았다). 같은 차례 안에서는 계산 줄 차례가 아니라
      차이가 작은 짝부터 정한다. 시트에서 그 칸을 한 줄도 안 쳤으면 빨강 '시트에 없음' 대신 회색 '아직 안 침'. */
  function compare(lines, rows) {
    var calcLines = (lines || []).filter(function (l) { return !l.head; });
    var used = rows.map(function () { return false; });
    var hit = calcLines.map(function () { return null; });
    var typed = {}, res = [];
    rows.forEach(function (r) { typed[r.sec] = true; });
    [exact, nearSameQty, oneDim, nearOtherQty].forEach(function (test) {
      var pairs = [];
      calcLines.forEach(function (l, li) {
        if (hit[li]) { return; }
        rows.forEach(function (r, i) {
          var m = (used[i] || r.bojo || r.sec !== l.sec) ? null : test(r, l);
          if (m) { pairs.push({ li: li, i: i, m: m }); }
        });
      });
      pairs.sort(function (x, y) { return (x.m.d - y.m.d) || (x.li - y.li) || (x.i - y.i); });
      pairs.forEach(function (p) {
        if (!hit[p.li] && !used[p.i]) { used[p.i] = true; hit[p.li] = p; }
      });
    });
    calcLines.forEach(function (l, li) {
      var h = hit[li], r = h && rows[h.i], got;
      if (!h) { got = typed[l.sec] ? { kind: 'bad', note: '시트에 없음' } : { kind: 'todo', note: '아직 안 침' }; }
      else if (h.m.kind) { got = h.m; }
      else if (r.q === l.q) { got = { kind: 'ok', note: '같음' }; }
      else { got = { kind: 'bad', note: '수량 다름(시트 ' + r.q + ')' }; }
      res.push({ sec: l.sec, text: l.text, kind: got.kind, note: got.note });
      if (!l.ea) { return; }
      var ea = { sec: '손잡이', text: 'ㄴ피닉스바 ' + l.ea + 'EA', kind: got.kind, note: got.note };   // 문 줄이 없으면 같이 없음
      if (h) { ea.kind = r.ea === l.ea ? 'ok' : 'bad'; ea.note = r.ea === l.ea ? '같음' : (r.ea ? '시트 ' + r.ea + 'EA' : '시트에 없음'); }
      res.push(ea);
    });
    rows.forEach(function (r, i) {
      if (!used[i]) { res.push({ sec: r.sec, text: r.text, kind: 'extra', note: r.bojo ? '보조목은 아직 계산 안 함' : '계산에 없음' }); }
    });
    return res;
  }

  window.FomsBomCalc = {
    LINES: LINES, LINE_NAMES: LINE_NAMES, HANDLES: HANDLES, NOMOLD: NOMOLD,
    sanitize: sanitize, emptyInputs: emptyInputs, calc: calc, toText: toText,
    parseBom: parseBom, compare: compare, guessLine: guessLine, guessHandle: guessHandle, parseSpec: parseSpec
  };
})();
