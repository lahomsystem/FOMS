/**
 * 도면 마법사 — AI 도면팀원 검수 메모 규칙(시트를 읽기만 한다 — 고치지 않는다).
 *
 * 설계 정본: docs/plans/2026-10-27-drawing-ai-teammate-spec.md §2 A1 (2026-10-27 사용자 승인 "추천대로")
 * - [저장] · [일괄 저장](= 전달 대기함에 넣기) 때 시트를 읽어 확실한 것만 메모한다:
 *   머리칸 빈칸(고객명 · 연락처 · 주소 · 영업 담당) · 미분류 그림 · 같은 그림 두 번 · 테두리 밖 그림 ·
 *   치수 글자 8px 아래(자동 배치와 같은 잣대) · 자재표 계산 칸과 다른 줄(계산 칸을 쓴 시트만).
 * - 시트 사이 겹친 그림 id 는 저장 직전 sheet-ids.js 가 떼어 내므로 메모하지 않는다.
 * - 찾은 것마다 key 가 있다. [끄기] 한 key 는 그 시트에서 다시 메모하지 않는다(sheet.review.off).
 *   한 번이라도 메모한 key 는 sheet.review.seen — 학습 요약이 메모마다 보인 수 · 끈 수를 세어 쓸모없는 메모를 뺀다.
 * - 규칙 하나가 터져도 다른 메모 · 저장은 그대로 간다.
 *
 * window.FomsReviewMemo = { check(sheet, ctx) → [memo], note(sheet, memos) → review|null, off(sheet, memo) → review|null,
 *   sanitize(review) → review|null, keyOf(text), KEY_RE, MAX_KEYS }
 *   ctx    : { unsure: '미분류', border: {x0,y0,x1,y1}, rectOf(o) → {x,y,w,h}|null(모르면 그 그림은 안 본다),
 *              textOf(o) → 치수 글자 높이(원본 px)|0, minText: 8, bom: FomsBomCalc(parseBom · compare)|null }
 *   memo   : { rule, keys: [key], text, ids: [객체 id], field: 머리칸 key|null }
 *   review : { off?: [key], seen?: [key] } — 둘 다 비면 null(시트에 남기지 않는다)
 *   (node 로 시험한다 — tests/domains/test_drawing_review_memo.py)
 */
(function () {
  'use strict';
  if (window.FomsReviewMemo) { return; }

  var KEY_RE = /^[0-9A-Za-z가-힣:_.-]{1,40}$/;   // 서버 계약(foms/api/drawing/wizard.py _validate_review)과 같다
  var MAX_KEYS = 40;
  var EDGE = 2;        // 테두리에 딱 붙인 그림은 밖이 아니다(px)
  var BOM_SHOW = 3;    // 자재표 다른 줄은 3줄까지 적고 나머지는 '외 N줄'
  var HEAD = [['customer_name', '고객명'], ['phone', '연락처'], ['address', '주소'], ['sales_manager', '영업 담당']];
  var NO_TEXT = { '사진': true, '그림 아님': true };   // 치수 글자를 따지지 않는 종류

  function images(s) { return ((s && s.objects) || []).filter(function (o) { return o && o.type === 'image'; }); }
  function blank(v) { return typeof v !== 'string' || !v.trim(); }
  function idOf(o) { return o.id; }
  function keys(v) { return Array.isArray(v) ? v.filter(function (k) { return typeof k === 'string' && KEY_RE.test(k); }) : []; }

  /** 자재표 칸 이름(SR · 문 폭 …) → key 조각. 쓸 수 없는 글자는 빼고 빈칸은 '_'. */
  function keyOf(text) {
    return String(text == null ? '' : text).trim().replace(/\s+/g, '_').replace(/[^0-9A-Za-z가-힣_.-]/g, '').slice(0, 30) || 'x';
  }

  /** 앞뒤 순서를 지키며 합친다 — 넘치면 오래된 것부터 버린다. */
  function merge(a, b) {
    var out = [];
    keys(a).concat(keys(b)).forEach(function (k) { if (out.indexOf(k) < 0) { out.push(k); } });
    return out.slice(-MAX_KEYS);
  }

  function texts(s) {
    return ((s && s.objects) || []).filter(function (o) { return o && o.type === 'text'; }).map(function (o) { return o.text; });
  }

  function n(fs) { return fs[0].ids.length; }

  /* 규칙: [이름, 찾기(sheet, ctx) → [{ key, ids?, field?, name?, px?, note? }], 메모 글(찾은 것들, ctx)] — 메모 순서도 이 순서 */
  var RULES = [
    ['head', function (s) {
      var form = (s && s.form) || {};
      return HEAD.filter(function (f) { return blank(form[f[0]]); })
        .map(function (f) { return { key: 'head:' + f[0], field: f[0], name: f[1] }; });
    }, function (fs) {
      return '머리칸이 비었어요 — ' + fs.map(function (f) { return f.name; }).join(' · ');
    }],
    ['unsorted', function (s, ctx) {
      var ids = images(s).filter(function (o) { return o.part && o.part.label === ctx.unsure; }).map(idOf);
      return ids.length ? [{ key: 'unsorted', ids: ids }] : [];
    }, function (fs) {
      return '미분류 그림 ' + n(fs) + '장 — 종류를 골라 주세요';
    }],
    ['dup', function (s) {
      var seen = {}, ids = [];
      images(s).forEach(function (o) {
        if (!o.key) { return; }
        if (seen[o.key]) { ids.push(o.id); } else { seen[o.key] = true; }
      });
      return ids.length ? [{ key: 'dup', ids: ids }] : [];
    }, function (fs) {
      return '같은 그림이 두 번 놓였어요 — ' + n(fs) + '장';
    }],
    ['outside', function (s, ctx) {
      var B = ctx.border, ids = [];
      if (!B || typeof ctx.rectOf !== 'function') { return []; }
      images(s).forEach(function (o) {
        var r = ctx.rectOf(o);
        if (r && (r.x < B.x0 - EDGE || r.y < B.y0 - EDGE || r.x + r.w > B.x1 + EDGE || r.y + r.h > B.y1 + EDGE)) { ids.push(o.id); }
      });
      return ids.length ? [{ key: 'outside', ids: ids }] : [];
    }, function (fs) {
      return '테두리 밖으로 나간 그림 ' + n(fs) + '장 — 전달 그림에서 잘려 보일 수 있어요';
    }],
    ['text', function (s, ctx) {
      var ids = [], least = Infinity, min = ctx.minText > 0 ? ctx.minText : 8;
      if (typeof ctx.textOf !== 'function') { return []; }
      images(s).forEach(function (o) {
        if (o.part && NO_TEXT[o.part.label]) { return; }
        var tx = ctx.textOf(o), nw = o.natural_w || o.w;
        if (!(tx > 0) || !(nw > 0) || !(o.w > 0)) { return; }
        var px = tx * o.w / nw;   // 치수 글자가 시트에서 보이는 높이(자동 배치 part-layout.js textPx 와 같은 잣대)
        if (px < min) { ids.push(o.id); least = Math.min(least, px); }
      });
      return ids.length ? [{ key: 'text', ids: ids, px: least }] : [];
    }, function (fs, ctx) {
      var min = ctx.minText > 0 ? ctx.minText : 8;
      return '치수 글자가 ' + min + 'px 보다 작은 그림 ' + n(fs) + '장(가장 작은 글자 약 ' + Math.max(1, Math.round(fs[0].px)) +
        'px) — 시트를 나누면 커져요';
    }],
    ['bom', function (s, ctx) {
      var C = ctx.bom, out = (s && s.calc && typeof s.calc.out === 'string') ? s.calc.out : '';
      if (!C || typeof C.parseBom !== 'function' || typeof C.compare !== 'function' || !out.trim()) { return []; }
      // 계산 칸이 마지막으로 계산해 시트에 남긴 글자(calc.out)를 다시 읽어, 시트에 친 자재표와 줄마다 맞춰 본다.
      var got = {}, fs = [];
      C.compare(C.parseBom([out]), C.parseBom(texts(s))).forEach(function (r) {
        if (r.kind !== 'bad') { return; }
        var key = 'bom:' + keyOf(r.sec);
        if (got[key]) { return; }
        got[key] = true;
        fs.push({ key: key, name: r.sec, note: r.note });
      });
      return fs;
    }, function (fs) {
      var shown = fs.slice(0, BOM_SHOW).map(function (f) { return f.name + ' ' + f.note; }).join(' · ');
      return '자재표가 계산 칸과 달라요 — ' + shown + (fs.length > BOM_SHOW ? ' 외 ' + (fs.length - BOM_SHOW) + '줄' : '');
    }]
  ];

  /** 시트 하나를 읽어 메모 목록을 낸다. [끄기] 한 key 는 뺀다. */
  function check(sheet, ctx) {
    var c = ctx || {}, off = {}, memos = [];
    keys(sheet && sheet.review && sheet.review.off).forEach(function (k) { off[k] = true; });
    RULES.forEach(function (R) {
      var fs;
      try { fs = R[1](sheet, c) || []; } catch (e) { fs = []; }
      fs = fs.filter(function (f) { return f && KEY_RE.test(f.key) && !off[f.key]; });
      if (!fs.length) { return; }
      var ids = [];
      fs.forEach(function (f) { (f.ids || []).forEach(function (id) { if (ids.indexOf(id) < 0) { ids.push(id); } }); });
      var text;
      try { text = R[2](fs, c); } catch (e) { return; }
      memos.push({ rule: R[0], keys: fs.map(function (f) { return f.key; }), text: text, ids: ids, field: fs[0].field || null });
    });
    return memos;
  }

  function sanitize(review) {
    if (!review || typeof review !== 'object') { return null; }
    var off = merge(review.off, []), seen = merge(review.seen, []), out = {};
    if (off.length) { out.off = off; }
    if (seen.length) { out.seen = seen; }
    return (off.length || seen.length) ? out : null;
  }

  function allKeys(memos) {
    var out = [];
    (memos || []).forEach(function (m) { out = out.concat((m && m.keys) || []); });
    return out;
  }

  /** 이번에 보인 메모 key 를 sheet.review.seen 에 더한 새 기록(시트는 안 바꾼다 — 부르는 쪽이 대입). */
  function note(sheet, memos) {
    var r = sanitize(sheet && sheet.review) || {};
    return sanitize({ off: r.off, seen: merge(r.seen, allKeys(memos)) });
  }

  /** [끄기] — 그 메모의 key 를 off · seen 에 더한 새 기록. */
  function off(sheet, memo) {
    var r = sanitize(sheet && sheet.review) || {}, k = allKeys([memo]);
    return sanitize({ off: merge(r.off, k), seen: merge(r.seen, k) });
  }

  window.FomsReviewMemo = { check: check, note: note, off: off, sanitize: sanitize, keyOf: keyOf, KEY_RE: KEY_RE, MAX_KEYS: MAX_KEYS };
})();
