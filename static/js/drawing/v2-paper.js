/**
 * 도면 마법사 V2 — 종이 위 칸 머리 · 특이 상자 · 강조 테두리 · 자재표 칸 선 · 배율 · 고정 · 문제 표시 · 아래 띠 '장 N/M'.
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §3 (화면 시안 K2-WizardAuto)
 * - 칸 머리는 #dws-v2-slots(스테이지 안 DOM)에 그려 PNG 에 찍힌다. 자리는 칸 그림 · 글자의 실제 상자(묶음 테두리) 바로 위 —
 *   손으로 옮겨도 머리가 따라간다. 칸으로 정리한 시트(폼 v2_layout)에서만 그린다.
 *   고정 그림(손으로 옮김 · 잠금 · 돌림)은 칸 밖에 있을 수 있어 머리 자리에서 뺀다(칸 그림이 다 고정이면 그대로 — v2-slots slotBox) —
 *   빼지 않았더니 머리가 다른 칸 위로 길게 뻗었다.
 * - 칸 글자는 종이 왼쪽 위부터 읽는 순서(v2-slots letters — v2-plan build 가 plan.letters 로 붙인다). 왼쪽 카드(v2-left.js)도
 *   같은 plan.letters 를 읽는다. 정리 전 시트는 예전 순서 그대로.
 * - 종류 모르는 그림 칸 머리는 화면에만(#dws-v2-badges) 주황 '? 종류 확인 N장' — 예전엔 'D 기타 그림'이 전달 도면에 찍혔다.
 *   큰 그림 칸 곁글은 이름을 붙인다('현장규격 1500 · 색상 화이트') — '1500'만 있어 무슨 숫자인지 몰랐다.
 * - 배율 표시(108% 등)는 #dws-v2-badges(.dws-ui)라 PNG 에 안 찍힌다. 머리 오른쪽 끝 위에 띄운다(아래 끝 = 머리 글 윗선) —
 *   머리 가운데에 걸쳤더니 좁은 칸에서 글을 가렸다('B 서랍 단면 · 부[32%]세', 스테이징 주문 4385).
 *   자재표 칸은 배율이 없어 표시도 없다(예전 '직접 입력'은 눌리지 않는데 단추처럼 보였다).
 * - 자동 배치 모드에서만(화면에만): 고정 그림 왼쪽 위 '고정' — 다시 배치해도 그대로인 그림. 서로 겹친 그림 · 치수 글자가
 *   8px 밑인 그림은 주황 테두리와 딱지('그림 겹침' · '글자 작음 6px') — 사람이 눈으로 하나하나 찾지 않게.
 *
 * window.FomsV2Paper = { render(view), HEAD, bbox(list), problems(sheet, plan) → { id: [딱지 글] } }
 *   view: { sheet, plan, pct: {id: 비율}, minId, autoPhoto: {id:true}, sheets: 시트 수, mode, layer, badges, pageTotal }
 */
(function () {
  'use strict';
  if (window.FomsV2Paper) { return; }

  var HEAD = 24, HEAD_MIN_W = 132, NOTES_HEAD_W = 300, NOTE_PAD_X = 7, NOTE_PAD_Y = 3, STAMP_PAD = 10, COLGAP = 18;
  var PILL_UP = 18;   // 배율 표시 위끝 = 머리 위 18px(높이 22 — wizard-v2.css .dws-v2-pill): 머리 글 윗선까지만 내려온다
  var OVER_TOL = 2, WARN_PAD = 3, PIN_ROW = 24;   // 겹침은 2px 넘게만 · 문제 테두리는 그림 밖 3px · 딱지는 '고정' 표시 아래 줄

  function S() { return window.FomsV2Slots; }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text != null) { n.textContent = text; }
    return n;
  }
  function place(n, x, y, w, h) {
    n.style.left = Math.round(x) + 'px';
    n.style.top = Math.round(y) + 'px';
    if (w != null) { n.style.width = Math.round(w) + 'px'; }
    if (h != null) { n.style.height = Math.round(h) + 'px'; }
    return n;
  }
  function boxOf(o) {
    return o.type === 'text' ? window.FomsV2Slots.textBox(o) : { x: o.x, y: o.y, w: o.w, h: o.h };
  }
  function bbox(list) {
    if (!list.length) { return null; }
    var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    list.forEach(function (o) {
      var b = boxOf(o);
      x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y); x1 = Math.max(x1, b.x + b.w); y1 = Math.max(y1, b.y + b.h);
    });
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  }
  function pctText(p) { return Math.round(p * 100) + '%'; }

  /** 칸마다 머리 글 — { badge, name, meta, side, check: 화면에만 그리는 주황 머리 }. */
  function headText(key, view) {
    var plan = view.plan, form = (view.sheet && view.sheet.form) || {}, letters = plan.letters, g = plan.g;
    if (key === 'photo') { return { badge: '사진', name: '실측 사진', meta: '현장' }; }
    if (key === 'bom') { return { badge: '자재', name: '자재표', meta: '열 ' + g.bom.length }; }
    if (key === 'notes') { return { badge: '특이', name: '특이 사항', side: '실선 제작 · 점선 현장' }; }
    if (key === 'main' || key === 'iso') {
      var labels = (g[key] || []).map(function (o) { return g.labels[o.id] || ''; });
      var side = [];
      if (labels.some(function (l) { return /내부$/.test(l); })) { side.push('내부'); }
      if (labels.some(function (l) { return /도어$/.test(l); })) { side.push('도어'); }
      // 아래 띠 칸 이름을 붙인다 — 현장규격은 '폭×깊이×높이' 또는 영업이 친 규격 글 그대로라 '폭'이라고 단정하지 않는다
      var meta = [['현장규격', form.site_spec], ['색상', form.color]].map(function (p) {
        var v = String(p[1] || '').replace(/\s+/g, ' ').trim();
        return v ? p[0] + ' ' + v : '';
      }).filter(Boolean).join(' · ');
      var name = window.FomsV2Slots.title(key, g, plan.kitchen);   // 칸 이름 = 든 그림 종류(제품 이름이 아니다)
      if (key === 'iso') { return { badge: letters.iso || 'B', name: name, side: side.join(' · ') }; }
      return { badge: letters.main || 'A', name: name, meta: plan.kitchen ? '' : meta, side: side.join(' · ') };
    }
    if (key === 'detail') { return { badge: letters.detail || 'B', name: window.FomsV2Slots.title(key, g, plan.kitchen) }; }
    if (key === 'plan') { return { badge: letters.plan || 'C', name: '평면 · 상판' }; }
    return { badge: '?', name: '종류 확인', meta: g.unsorted.length + '장', check: true };   // 종류 모르는 그림 — 화면에만
  }

  function drawHead(layer, key, b, view) {
    var t = headText(key, view), w = Math.max(b.w, key === 'notes' ? NOTES_HEAD_W : HEAD_MIN_W);
    var head = place(el('div', 'dws-v2-head' + (t.check ? ' dws-v2-head-check' : '')), b.x, b.y - HEAD, w, HEAD);
    var badge = el('span', 'dws-v2-head-badge' + (t.badge.length > 1 ? ' dws-v2-head-badge-word' : ''), t.badge);
    head.appendChild(badge);
    head.appendChild(el('span', 'dws-v2-head-name', t.name));
    if (t.meta) { head.appendChild(el('span', 'dws-v2-head-meta', t.meta)); }
    if (t.side) { head.appendChild(el('span', 'dws-v2-head-side', t.side)); }
    layer.appendChild(head);
    return { x: b.x, y: b.y - HEAD, w: w, h: HEAD };
  }

  function drawBomLines(layer, bom) {
    var cols = bom.map(boxOf).sort(function (a, c) { return a.x - c.x; });
    var top = Math.min.apply(null, cols.map(function (c) { return c.y; }));
    var bottom = Math.max.apply(null, cols.map(function (c) { return c.y + c.h; }));
    cols.forEach(function (c) {
      layer.appendChild(place(el('div', 'dws-v2-bom-line'), c.x + c.w + COLGAP / 2, top, 1, bottom - top));
    });
  }

  function drawNotes(layer, notes) {
    notes.forEach(function (o) {
      var b = boxOf(o);
      var kind = window.FomsV2Slots.noteKind(o) === 'site' ? ' dws-v2-note-site' : '';
      layer.appendChild(place(el('div', 'dws-v2-note' + kind), b.x - NOTE_PAD_X, b.y - NOTE_PAD_Y,
        b.w + 2 * NOTE_PAD_X, b.h + 2 * NOTE_PAD_Y));
    });
  }

  function drawStamp(layer, o) {
    var b = boxOf(o);
    layer.appendChild(place(el('div', 'dws-v2-stamp'), b.x - STAMP_PAD, b.y - STAMP_PAD, b.w + 2 * STAMP_PAD, b.h + 2 * STAMP_PAD));
  }

  /** 배율 표시 — 칸 머리 오른쪽 끝 위(화면에만). */
  function drawPill(badges, head, text, tone) {
    var pill = el('span', 'dws-v2-pill dws-v2-pill-' + tone, text);
    pill.style.left = Math.round(head.x + head.w) + 'px';
    pill.style.top = Math.round(head.y - PILL_UP) + 'px';
    badges.appendChild(pill);
  }

  /** 칸 배율 표시 { text, tone } — 없으면 null. 자재표 · 특이 사항 글자는 크기를 바꾸지 않아 없다. */
  function pillOf(key, list, view) {
    if (key === 'bom' || key === 'notes') { return null; }
    if (key === 'photo') {
      var auto = list.some(function (o) { return view.autoPhoto && view.autoPhoto[o.id]; });
      return auto ? { text: '사진 자동', tone: 'green' } : null;
    }
    var pct = view.pct || {}, ps = list.map(function (o) { return pct[o.id]; }).filter(function (v) { return v > 0; });
    if (!ps.length) { return null; }
    var hasMin = list.some(function (o) { return o.id === view.minId; });
    return { text: pctText(Math.min.apply(null, ps)), tone: hasMin ? 'orange' : (key === 'main' || key === 'iso' ? 'blue' : 'gray') };
  }

  /** 고정 표시 — 그림 왼쪽 위 '고정', 손으로 옮겨 고정한 칸 머리 위 글자(g.pins — v2-text.js)는 글자 왼쪽 위(자재표는 줄 첫 열만, 화면에만). */
  function drawPins(badges, sheet, g) {
    var bomDone = false;
    (sheet.objects || []).forEach(function (o) {
      if (o.type === 'image' && g.fixed[o.id]) { badges.appendChild(place(el('span', 'dws-v2-pin', '고정'), (o.x || 0) + 4, (o.y || 0) + 4)); }
      if (o.type !== 'text' || !g.pins || !g.pins[o.id] || (bomDone && S().role(o) === 'bom')) { return; }
      var b = boxOf(S().role(o) === 'bom' ? g.bom.filter(function (x) { return g.pins[x.id]; }).sort(function (p, q) { return p.x - q.x; })[0] : o);
      bomDone = bomDone || S().role(o) === 'bom';
      badges.appendChild(place(el('span', 'dws-v2-pin dws-v2-pin-text', '고정'), b.x - 2, b.y - 8));   // 글자 윗선에 걸친 작은 딱지
    });
  }

  /** 문제 그림 — { id: ['그림 겹침', '글자 작음 6px'] }.
      겹침 = 돌린 모양을 감싼 상자(v2-plan stayBox)끼리 가로 · 세로 모두 2px 넘게 겹침(사진도 센다).
      작은 글자 = 치수 글자(원본 px × 지금 높이 ÷ 원본 높이)가 8px 밑 — 자동 배치 · 검수 메모와 같은 잣대. 사진 · 종류 모르는 그림은 뺀다. */
  function problems(sheet, plan) {
    var imgs = ((sheet && sheet.objects) || []).filter(function (o) { return o.type === 'image'; }), out = {}, skip = {};
    var boxes = imgs.map(function (o) { return window.FomsV2Plan.stayBox(o); }), items = (plan && plan.items) || {};
    function add(id, text) { (out[id] = out[id] || []).push(text); }
    function over(p, q) {
      return Math.min(p.x + p.w, q.x + q.w) - Math.max(p.x, q.x) > OVER_TOL && Math.min(p.y + p.h, q.y + q.h) - Math.max(p.y, q.y) > OVER_TOL;
    }
    imgs.forEach(function (o, i) { if (boxes.some(function (q, j) { return j !== i && over(boxes[i], q); })) { add(o.id, '그림 겹침'); } });
    if (plan && plan.g) { plan.g.photo.concat(plan.g.unsorted).forEach(function (o) { skip[o.id] = true; }); }
    imgs.forEach(function (o) {
      var it = items[o.id], px = it && it.tx > 0 && it.nh > 0 ? it.tx * o.h / it.nh : null;
      if (px != null && !skip[o.id] && px < window.FomsV2Layout.MIN_TEXT) { add(o.id, '글자 작음 ' + Math.max(1, Math.floor(px)) + 'px'); }
    });
    return out;
  }

  /** 문제 표시 — 그림 둘레 주황 테두리 + 왼쪽 위 딱지(고정 그림은 '고정' 표시 아래 줄). */
  function drawWarns(badges, sheet, plan) {
    var bad = problems(sheet, plan);
    (sheet.objects || []).forEach(function (o) {
      if (o.type !== 'image' || !bad[o.id]) { return; }
      var b = window.FomsV2Plan.stayBox(o);
      badges.appendChild(place(el('div', 'dws-v2-warn'), b.x - WARN_PAD, b.y - WARN_PAD, b.w + 2 * WARN_PAD, b.h + 2 * WARN_PAD));
      badges.appendChild(place(el('span', 'dws-v2-warn-tag', bad[o.id].join(' · ')), b.x + 4, b.y + 4 + (plan.g.fixed[o.id] ? PIN_ROW : 0)));
    });
  }

  function render(view) {
    var layer = view.layer, badges = view.badges, sheet = view.sheet, plan = view.plan;
    if (!layer) { return; }
    layer.textContent = '';
    if (badges) { badges.textContent = ''; }
    if (view.pageTotal) { view.pageTotal.textContent = '/ ' + Math.max(1, view.sheets || 1); }
    if (!sheet || !plan) { return; }
    var g = plan.g;
    if (g.notes.length) { drawNotes(layer, g.notes); }
    if (g.stamp) { drawStamp(layer, g.stamp); }
    if (!plan.laid) { return; }   // 칸으로 정리하기 전에는 머리를 그리지 않는다(예전 화면에서 놓은 그대로)
    if (g.bom.length > 1) { drawBomLines(layer, g.bom); }
    ['photo', 'bom', 'notes', 'main', 'iso', 'detail', 'plan', 'unsorted'].forEach(function (key) {
      var b = S().slotBox(g, key), into = key === 'unsorted' ? badges : layer;   // 종류 모르는 그림 머리는 화면에만
      if (!b || !into) { return; }
      var head = drawHead(into, key, b, view), pill = badges ? pillOf(key, g[key] || [], view) : null;
      if (pill) { drawPill(badges, head, pill.text, pill.tone); }
    });
    if (badges && view.mode === 'auto') { drawPins(badges, sheet, g); drawWarns(badges, sheet, plan); }
  }

  window.FomsV2Paper = { render: render, HEAD: HEAD, bbox: bbox, problems: problems };
})();
