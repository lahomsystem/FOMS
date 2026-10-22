/**
 * 도면 마법사 — 자재표 계산(순수 계산, 화면을 건드리지 않는다).
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.3 · §3.6
 * - 식은 지난 자재표 670장에서 가장 많이 쓴 값을 찾은 초안이다(도면팀 확인 전).
 *   식에 들어가는 숫자(rules)는 서버 설정(/api/orders/drawing-wizard/bom-rules)에서 받는다.
 * - 옆벽 SR 은 넣은 값을 그대로 적는다. 보조목·EP 41 띠·주방 문 높이는 규칙을 못 찾아 계산하지 않는다.
 * - 시트에 사람이 친 자재표 글자를 읽어 계산과 줄마다 맞춰 본다(같음·여유·짧음·다름).
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
  function doorHeight(s, r) {
    if (s.door_h > 0) { return { h: s.door_h, why: '직접 넣은 값' }; }
    if (s.line === 'nomold' && s.nomold === 'ceiling') {
      return { h: Math.floor((s.H - r.nomold_cut) / r.nomold_step) * r.nomold_step,
        why: '천장 ' + s.H + ' − ' + r.nomold_cut + ' → ' + r.nomold_step + ' 단위 내림' };
    }
    var std = r.door_std_heights;
    var ok = std.filter(function (h) { return h <= s.H - r.door_ceiling_margin; });
    return { h: ok.length ? ok[ok.length - 1] : std[0],
      why: '표준 문 중 천장 ' + s.H + ' − ' + r.door_ceiling_margin + ' 이하에서 가장 큰 것' + (s.line === 'other' ? '(냉장고장·그 밖은 추정)' : '') };
  }
  function doorWidth(w, n, s, r) {
    if (s.line === 'slide') { return { w: w, why: '슬라이딩 문 = 모듈 폭 ' + w }; }
    var ph = s.handle === 'phoenix';
    if (n === 1) {
      var single = ph ? r.door_gap_phoenix_single : r.door_gap_other_single;
      return { w: w - single, why: '외짝 ' + w + ' − ' + single };
    }
    var pair = ph ? r.door_gap_phoenix_pair : r.door_gap_other_pair;
    return { w: Math.floor((w - pair) / n), why: '(' + w + ' − ' + pair + ') ÷ ' + n + ' 내림' };
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
          '(' + m.w + ' − ' + r.maida_w_cut + ') × (' + zone + ' ÷ ' + m.drawers + ' − ' + r.maida_h_cut + ')');
      }
      if (m.rods > 0) { add(rod, m.w - r.rod_cut, null, m.rods, m.w + ' − ' + r.rod_cut); }
    });
    if (dh && s.H > 0 && s.W > 0 && s.H - dh.h > 0) {
      var gap = s.H - dh.h, q = Math.ceil(s.W / r.sheet_len);
      var small = gap <= r.sr_small_gap;
      var top = small ? r.sr_small_value : Math.ceil((gap - r.sr_minus) / r.sr_step) * r.sr_step;
      add(sr, top, r.sheet_len, q, (small ? '위 틈 ' + gap + '(' + r.sr_small_gap + ' 이하) → ' + top
        : '위 틈 ' + gap + ' − ' + r.sr_minus + ' → ' + r.sr_step + ' 단위 올림') + ' · 폭 ' + s.W + ' ÷ ' + r.sheet_len + ' 올림 ' + q + '장');
    }
    [s.sr_l, s.sr_r].forEach(function (g) { if (g > 0) { add(sr, g, r.sheet_len, 1, '옆벽 SR(넣은 값)'); } });
    if (s.ep > 0 && s.D > 0) {
      var plus = (s.line === 'mold' || s.line === 'nomold') ? r.ep_plus_hinged : 0;
      add(ep, s.D + plus, r.sheet_len, s.ep, '깊이 ' + s.D + (plus ? ' + ' + plus : ' 그대로') + ' · 길이 ' + r.sheet_len);
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

  function nearMiss(r, l) {
    var da = r.a - l.a, db = (r.b == null || l.b == null) ? 0 : r.b - l.b;
    var d = (da === 0) ? db : (db === 0 ? da : 0);
    if (d >= 1 && d <= 20) { return { kind: 'warn', note: '여유 +' + d + '(시트 ' + r.text + ')' }; }
    if (d <= -1 && d >= -20) { return { kind: 'bad', note: '짧음 ' + d + '(시트 ' + r.text + ')' }; }
    return null;
  }

  /** 계산 줄 ↔ 시트 줄 → [{sec, text, kind: ok|warn|bad|extra, note}]. */
  function compare(lines, rows) {
    var used = rows.map(function () { return false; });
    var res = [];
    function find(l, test) {
      for (var i = 0; i < rows.length; i++) {
        if (!used[i] && !rows[i].bojo && rows[i].sec === l.sec && test(rows[i])) { return i; }
      }
      return -1;
    }
    (lines || []).filter(function (l) { return !l.head; }).forEach(function (l) {
      var miss = null;
      var idx = find(l, function (r) { return r.a === l.a && r.b === l.b; });
      if (idx < 0) { idx = find(l, function (r) { miss = nearMiss(r, l); return !!miss; }); }
      if (idx < 0) { res.push({ sec: l.sec, text: l.text, kind: 'bad', note: '시트에 없음' }); return; }
      used[idx] = true;
      var r = rows[idx];
      if (miss) { res.push({ sec: l.sec, text: l.text, kind: miss.kind, note: miss.note }); }
      else if (r.q === l.q) { res.push({ sec: l.sec, text: l.text, kind: 'ok', note: '같음' }); }
      else { res.push({ sec: l.sec, text: l.text, kind: 'bad', note: '수량 다름(시트 ' + r.q + ')' }); }
      if (l.ea) {
        var same = r.ea === l.ea;
        res.push({ sec: '손잡이', text: 'ㄴ피닉스바 ' + l.ea + 'EA', kind: same ? 'ok' : 'bad', note: same ? '같음' : (r.ea ? '시트 ' + r.ea + 'EA' : '시트에 없음') });
      }
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
