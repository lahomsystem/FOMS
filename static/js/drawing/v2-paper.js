/**
 * 도면 마법사 V2 — 종이 위 칸 머리 · 특이 상자 · 강조 테두리 · 자재표 칸 선 · 배율 표시 · 아래 띠 '장 N/M'.
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §3 (화면 시안 K2-WizardAuto)
 * - 칸 머리는 #dws-v2-slots(스테이지 안 DOM)에 그려 PNG 에 찍힌다. 자리는 칸 그림 · 글자의 실제 상자(묶음 테두리) 바로 위 —
 *   손으로 옮겨도 머리가 따라간다. 칸으로 정리한 시트(폼 v2_layout)에서만 그린다.
 * - 배율 표시(108% 등)는 #dws-v2-badges(.dws-ui)라 PNG 에 안 찍힌다.
 *
 * window.FomsV2Paper = { render(view), HEAD }
 *   view: { sheet, plan, pct: {id: 비율}, minId, autoPhoto: {id:true}, sheets: 시트 수, layer, badges, pageTotal }
 */
(function () {
  'use strict';
  if (window.FomsV2Paper) { return; }

  var HEAD = 24, HEAD_MIN_W = 132, NOTES_HEAD_W = 300, NOTE_PAD_X = 7, NOTE_PAD_Y = 3, STAMP_PAD = 10, COLGAP = 18;

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

  /** 칸마다 머리 글 — { badge, name, meta, side }. */
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
      var meta = [form.site_spec, form.color].map(function (v) { return String(v || '').replace(/\s+/g, ' ').trim(); })
        .filter(Boolean).join(' · ');
      if (key === 'iso') { return { badge: letters.iso || 'B', name: '입체', side: side.join(' · ') }; }
      return { badge: letters.main || 'A', name: plan.kitchen ? '정면' : (String(form.product_name || '').trim() || '큰 그림'),
        meta: plan.kitchen ? '' : meta, side: side.join(' · ') };
    }
    if (key === 'detail') {
      var ls = (g.detail || []).map(function (o) { return g.labels[o.id]; });
      var name = ls.every(function (l) { return l === '서랍 단면'; }) ? '서랍 단면'
        : (ls.every(function (l) { return l === '부품 상세'; }) ? '부품 상세' : '상세');
      return { badge: letters.detail || 'B', name: name };
    }
    if (key === 'plan') { return { badge: letters.plan || 'C', name: '평면 · 상판' }; }
    return { badge: letters.unsorted || '?', name: '기타 그림' };
  }

  function drawHead(layer, key, b, view) {
    var t = headText(key, view), w = Math.max(b.w, key === 'notes' ? NOTES_HEAD_W : HEAD_MIN_W);
    var head = place(el('div', 'dws-v2-head'), b.x, b.y - HEAD, w, HEAD);
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

  /** 배율 표시 — 칸 머리 오른쪽 끝(화면에만). */
  function drawPill(badges, head, text, tone) {
    var pill = el('span', 'dws-v2-pill dws-v2-pill-' + tone, text);
    pill.style.left = Math.round(head.x + head.w) + 'px';
    pill.style.top = Math.round(head.y - 14) + 'px';
    badges.appendChild(pill);
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
    var pct = view.pct || {}, minId = view.minId;
    ['photo', 'bom', 'notes', 'main', 'iso', 'detail', 'plan', 'unsorted'].forEach(function (key) {
      var list = key === 'bom' ? g.bom : (key === 'notes' ? g.notes : (g[key] || []));
      var b = bbox(list);
      if (!b) { return; }
      var head = drawHead(layer, key, b, view);
      if (!badges) { return; }
      if (key === 'bom') { drawPill(badges, head, '직접 입력', 'gray'); return; }
      if (key === 'notes') { return; }
      if (key === 'photo') {
        if (list.some(function (o) { return view.autoPhoto && view.autoPhoto[o.id]; })) { drawPill(badges, head, '사진 자동', 'green'); }
        return;
      }
      var ps = list.map(function (o) { return pct[o.id]; }).filter(function (v) { return v > 0; });
      if (!ps.length) { return; }
      var low = Math.min.apply(null, ps);
      var hasMin = list.some(function (o) { return o.id === minId; });
      drawPill(badges, head, pctText(low), hasMin ? 'orange' : (key === 'main' || key === 'iso' ? 'blue' : 'gray'));
    });
  }

  window.FomsV2Paper = { render: render, HEAD: HEAD, bbox: bbox };
})();
