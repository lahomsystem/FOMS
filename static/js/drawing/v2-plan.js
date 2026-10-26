/**
 * 도면 마법사 V2 — 시트 → 칸 배치 계획 · 시트에 붙이기 · 나누기 묶음(순수 계산, 마법사 상태만 고친다).
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §2 · §4
 * - build: 칸 묶기(v2-slots) → 배치 입력(정면 · 입체 짝은 V1 FomsPartLayout.groups 그대로) → 틀 두 가지 계산(v2-layout).
 * - apply: 고른 틀의 자리를 객체에 넣는다. 그림은 part.arr 에 놓은 자리를 남기고(사람이 옮겼는지 가린다),
 *   자리에 그대로 있던 그림 안쪽에 가운데가 있는 글자 · 도형 · 펜은 그 그림을 따라 옮긴다(치수 메모가 떨어지지 않게).
 *   새로 올린 그림(arr 없음)은 아무것도 데려가지 않는다 — 올린 자리가 우연히 메모 위일 수 있다.
 * - 폼 칸: v2_layout = 지금 놓인 틀('band'|'column'), v2_pick = 사람이 고른 틀(''|'band'|'column'), v2_kind = 제품 종류,
 *   v2_ai = AI 칸 짐작(v2-slots parseGuess).
 *
 * window.FomsV2Plan = { build(sheet, ctx) → plan, apply(sheet, res, opts), splitGroups(plan), nowPct(plan) }
 *   ctx: { items(imgs) → [{id,nw,nh,tx,order,label}], baseline(imgs) → {id:{w,h}}, productText, settings }
 */
(function () {
  'use strict';
  if (window.FomsV2Plan) { return; }

  function S() { return window.FomsV2Slots; }
  function bySlot(list) { return list || []; }

  function settingsOf(ctx) {
    var s = (ctx && ctx.settings) || {};
    return { lowToUnsorted: s.lowToUnsorted !== false, photoFirst: s.photoFirst !== false,
      sameScale: s.sameScale !== false, lockMoved: s.lockMoved !== false };
  }

  /** 시트 → { g, kind, kindAuto, kitchen, letters, input, out, base, settings, laid, template, pick } */
  function build(sheet, ctx) {
    var form = (sheet && sheet.form) || {}, set = settingsOf(ctx);
    var kindAuto = S().detectKind(ctx && ctx.productText);
    var kind = form.v2_kind || kindAuto, kitchen = kind === 'kitchen';
    var g = S().group((sheet && sheet.objects) || [], { lowToUnsorted: set.lowToUnsorted, lockMoved: set.lockMoved, kitchen: kitchen,
      guess: S().parseGuess(form.v2_ai) });
    var imgs = [].concat(g.photo, g.main, g.iso, g.detail, g.plan, g.unsorted);
    var items = imgs.length && ctx.items ? ctx.items(imgs) : [], byId = {};
    items.forEach(function (it) { byId[it.id] = it; });
    function item(o) { var it = byId[o.id] || {}; return { id: o.id, nw: it.nw || o.w, nh: it.nh || o.h, tx: it.tx || 0, order: it.order || 0 }; }
    function movable(list) { return bySlot(list).filter(function (o) { return !g.fixed[o.id]; }); }
    var pairIn = movable(g.main.concat(g.iso, g.detail)).map(function (o) {
      var it = item(o);
      it.label = g.lay[o.id];   // 짐작 칸 그림은 짐작 이름표로 짝을 찾는다(미분류로 두면 '그 밖' 묶음이 된다)
      return it;
    });
    var grp = window.FomsPartLayout && pairIn.length ? window.FomsPartLayout.groups(pairIn) : { units: [], small: [] };
    var units = grp.units.map(function (u) {
      return { slot: kitchen && u.kind === 'iso' ? 'iso' : 'main',
        members: u.members.map(function (m) { return { id: m.id, nw: m.nw, nh: m.nh, tx: m.tx }; }) };
    });
    var promoted = {};
    grp.units.forEach(function (u) { u.members.forEach(function (m) { promoted[m.id] = true; }); });
    function strip(list) { return list.map(function (o) { var it = item(o); return { id: it.id, nw: it.nw, nh: it.nh, tx: it.tx }; }); }
    function box(o) { var b = S().textBox(o); return { id: o.id, w: b.w, h: b.h }; }
    var input = {
      photo: strip(movable(g.photo)),
      detail: strip(movable(g.detail).filter(function (o) { return !promoted[o.id]; })),
      plan: strip(movable(g.plan)),
      unsorted: strip(movable(g.unsorted)),
      units: units,
      bom: g.bom.filter(function (o) { return !o.locked; }).map(box),
      notes: g.notes.filter(function (o) { return !o.locked; }).map(box),
      stamp: g.stamp && !g.stamp.locked ? box(g.stamp) : null,
      base: imgs.length && ctx.baseline ? ctx.baseline(imgs) : {}
    };
    var pick = form.v2_pick === 'band' || form.v2_pick === 'column' ? form.v2_pick : '';
    var out = window.FomsV2Layout.compute(input, { sameScale: set.sameScale, photoFirst: set.photoFirst, prefer: pick });
    return { g: g, kind: kind, kindAuto: kindAuto, kitchen: kitchen, letters: S().letters(g, kitchen), input: input,
      out: out, base: input.base, settings: set, laid: form.v2_layout === 'band' || form.v2_layout === 'column',
      template: form.v2_layout || '', pick: pick, items: byId };
  }

  /** 지금 자리 기준 % — { id: 비율 } (기준이 없으면 원본 대비). 사진도 넣는다(화면이 뺀다). */
  function nowPct(plan, sheet) {
    var out = {}, base = plan.base || {}, hasBase = Object.keys(base).length > 0;
    ((sheet && sheet.objects) || []).forEach(function (o) {
      if (o.type !== 'image') { return; }
      var b = base[o.id], it = plan.items[o.id];
      if (hasBase) { if (b && b.h > 0) { out[o.id] = o.h / b.h; } }
      else if (it && it.nh > 0) { out[o.id] = o.h / it.nh; }
    });
    return out;
  }

  function inside(px, py, r) { return px >= r.x && px <= r.x + r.w && py >= r.y && py <= r.y + r.h; }

  function freeCenter(o) {
    if (o.points && o.points.length >= 2) {
      var xs = [], ys = [];
      for (var i = 0; i + 1 < o.points.length; i += 2) { xs.push(o.points[i]); ys.push(o.points[i + 1]); }
      return { x: (Math.min.apply(null, xs) + Math.max.apply(null, xs)) / 2, y: (Math.min.apply(null, ys) + Math.max.apply(null, ys)) / 2 };
    }
    if (o.type === 'text') { var b = S().textBox(o); return { x: b.x + b.w / 2, y: b.y + b.h / 2 }; }
    return { x: (o.x || 0) + (o.w || 0) / 2, y: (o.y || 0) + (o.h || 0) / 2 };
  }

  function follow(o, from, to) {
    var sx = from.w > 0 ? to.w / from.w : 1, sy = from.h > 0 ? to.h / from.h : 1;
    function X(v) { return Math.round(to.x + (v - from.x) * sx); }
    function Y(v) { return Math.round(to.y + (v - from.y) * sy); }
    if (o.points && o.points.length) {
      o.points = o.points.map(function (v, i) { return i % 2 ? Y(v) : X(v); });
      return;
    }
    o.x = X(o.x || 0);
    o.y = Y(o.y || 0);
    if ((o.type === 'rect' || o.type === 'ellipse') && o.w > 0 && o.h > 0) {
      o.w = Math.max(1, Math.round(o.w * sx));
      o.h = Math.max(1, Math.round(o.h * sy));
    }
  }

  /** 고른 틀(res)을 시트에 붙인다. opts.template = 'band'|'column'. 돌려주는 값 = 옮긴 객체 수. */
  function apply(sheet, res, opts) {
    if (!sheet || !res) { return 0; }
    var byId = {}, carriers = [], n = 0;
    (sheet.objects || []).forEach(function (o) { byId[o.id] = o; });
    res.moves.forEach(function (m) {
      var o = byId[m.id];
      if (o && o.type === 'image' && o.part && o.part.arr && !S().moved(o) && !o.locked) {
        carriers.push({ from: { x: o.x, y: o.y, w: o.w, h: o.h }, to: m });
      }
    });
    if (carriers.length) {
      (sheet.objects || []).forEach(function (o) {
        if (o.locked || S().role(o) !== 'free') { return; }
        var c = freeCenter(o), host = null;
        carriers.forEach(function (k) {
          if (inside(c.x, c.y, k.from) && (!host || k.from.w * k.from.h < host.from.w * host.from.h)) { host = k; }
        });
        if (host) { follow(o, host.from, host.to); n += 1; }
      });
    }
    res.moves.forEach(function (m) {
      var o = byId[m.id];
      if (!o) { return; }
      o.x = m.x;
      o.y = m.y;
      if (o.type === 'image') {
        o.w = m.w;
        o.h = m.h;
        if (o.part) { o.part.arr = [m.x, m.y, m.w, m.h]; }
      }
      n += 1;
    });
    sheet.form = sheet.form || {};
    sheet.form.v2_layout = (opts && opts.template) || res.template;
    return n;
  }

  /** 시트 2장으로 나눌 그림 묶음 — 큰 그림 짝 · 상세 · 평면을 원본 넓이로 반씩(짝은 가르지 않는다).
      [새 시트로 옮길 id 배열] 하나를 돌려준다(못 나누면 null). 사진 · 자재표 · 특이 사항은 이 시트에 남는다. */
  function splitGroups(plan) {
    var inp = plan && plan.input;
    if (!inp) { return null; }
    var blocks = inp.units.map(function (u) {
      return { ids: u.members.map(function (m) { return m.id; }), area: u.members.reduce(function (s, m) { return s + m.nw * m.nh; }, 0) };
    }).concat(inp.detail.concat(inp.plan).map(function (it) { return { ids: [it.id], area: it.nw * it.nh }; }));
    if (blocks.length < 2) { return null; }
    var total = blocks.reduce(function (s, b) { return s + b.area; }, 0), acc = 0, moved = [];
    blocks.forEach(function (b, i) {
      if (i === 0 || acc + b.area / 2 <= total / 2) { acc += b.area; return; }
      moved = moved.concat(b.ids);
    });
    return moved.length ? [moved] : null;
  }

  window.FomsV2Plan = { build: build, apply: apply, splitGroups: splitGroups, nowPct: nowPct, settingsOf: settingsOf };
})();
