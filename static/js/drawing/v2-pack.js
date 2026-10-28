/**
 * 도면 마법사 V2 — 칸 안에 그림 · 글자를 늘어놓는 계산 도구(순수 계산).
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §4
 * - 그림 크기: sameScale(기본) = 한 칸 그림은 같은 배율(1000 폭 모듈과 500 폭 모듈이 반 크기로) · 아니면 같은 높이.
 *   어느 쪽이든 원본의 MAX_UP(1.25)배까지만 키운다(V1 part-layout.js 와 같음).
 * - 짝(내부 · 도어)은 한 묶음으로 옆에 붙인다(묶음 안 간격 GAP).
 *
 * window.FomsV2Pack = { GAP, HEAD, MAX_UP, row(items, maxW, maxH, same), stack(items, maxW, maxH, same),
 *   shelves(groups, W, H, same, bare, hi), flow(boxes, W, gap), room(x, y, w, h, obstacles, groups, same),
 *   block(unit, t, same), search(hi, fits), tCap(units, same),   — 이 셋은 주 그림 크게(v2-hero.js)가 쓴다
 *   rows(items, r, same) → r 줄 묶음(stack 에 넘긴다 — 위 띠 상세 두 줄), areas(full, obstacles), hits(res, obstacles) }   — v2-layout
 *   item  = { id, nw, nh, tx } (원본 픽셀) · unit = { members: [item] } · group = { key, units: [unit] }
 *   결과 좌표는 칸 왼쪽 위(0,0) 기준 — 부르는 쪽이 칸 자리를 더한다.
 */
(function () {
  'use strict';
  if (window.FomsV2Pack) { return; }

  var GAP = 16, HEAD = 24, MAX_UP = 1.25, ITER = 32;

  function unitH(u) { return Math.max.apply(null, u.members.map(function (m) { return m.nh; })); }

  /** 묶음 하나를 값 t 로 놓을 크기. same 이면 t = 배율, 아니면 t = 묶음 높이(px). */
  function block(u, t, same) {
    var sc = same ? t : t / unitH(u);
    var ws = u.members.map(function (m) { return Math.max(1, Math.round(m.nw * sc)); });
    var hs = u.members.map(function (m) { return Math.max(1, Math.round(m.nh * sc)); });
    return { ws: ws, hs: hs, sc: sc, w: ws.reduce(function (a, b) { return a + b; }, 0) + GAP * (ws.length - 1),
      h: Math.max.apply(null, hs) };
  }

  /** t 의 위 한계 — 원본의 MAX_UP 배까지. */
  function tCap(units, same) {
    if (same) { return MAX_UP; }
    return MAX_UP * Math.min.apply(null, units.map(unitH));
  }

  function asUnits(items) { return (items || []).map(function (it) { return it.members ? it : { members: [it] }; }); }

  /** 가장 큰 t 를 이분 탐색 — fits(t) 가 참인 가장 큰 값(0 이면 못 놓음). */
  function search(hi, fits) {
    if (!(hi > 0)) { return 0; }
    if (fits(hi)) { return hi; }
    var lo = 0;
    for (var i = 0; i < ITER; i++) {
      var mid = (lo + hi) / 2;
      if (fits(mid)) { lo = mid; } else { hi = mid; }
    }
    return lo;
  }

  function placeRow(units, t, same, y0) {
    var x = 0, out = [], h = 0;
    units.forEach(function (u, i) {
      var bl = block(u, t, same);
      if (i) { x += GAP; }
      for (var k = 0, mx = x; k < u.members.length; mx += bl.ws[k] + GAP, k++) {
        out.push({ id: u.members[k].id, x: mx, y: y0 + bl.h - bl.hs[k], w: bl.ws[k], h: bl.hs[k], sc: bl.sc });
      }
      x += bl.w;
      h = Math.max(h, bl.h);
    });
    return { placed: out, w: x, h: h };
  }

  /** 한 줄에 가로로 — 폭 maxW · 높이 maxH 안에서 가장 크게. → { placed, w, h, t } */
  function row(items, maxW, maxH, same) {
    var units = asUnits(items);
    if (!units.length) { return { placed: [], w: 0, h: 0, t: 0 }; }
    var t = search(tCap(units, same), function (v) {
      var r = placeRow(units, v, same, 0);
      return r.w <= maxW && r.h <= maxH;
    });
    if (!(t > 0)) { return null; }
    var r = placeRow(units, t, same, 0);
    r.t = t;
    return r;
  }

  /** 세로로 쌓기 — 폭 maxW · 높이 maxH 안에서 가장 크게. → { placed, w, h, t } */
  function stack(items, maxW, maxH, same) {
    var units = asUnits(items);
    if (!units.length) { return { placed: [], w: 0, h: 0, t: 0 }; }
    function lay(v) {
      var y = 0, w = 0, out = [];
      units.forEach(function (u, i) {
        var r = placeRow([u], v, same, y + (i ? GAP : 0));
        out = out.concat(r.placed);
        y += r.h + (i ? GAP : 0);
        w = Math.max(w, r.w);
      });
      return { placed: out, w: w, h: y };
    }
    var t = search(tCap(units, same), function (v) { var r = lay(v); return r.w <= maxW && r.h <= maxH; });
    if (!(t > 0)) { return null; }
    var res = lay(t);
    res.t = t;
    return res;
  }

  /** 여러 칸(group)을 위에서부터 — 칸마다 머리(HEAD)를 두고 묶음을 줄로 채운다(넘치면 다음 줄).
      모든 칸이 같은 t(배율 · 높이)를 쓴다. bare = 머리 없이(bento 나머지 — 머리는 칸 전체 위에 하나). hi = t 위 한계(주 그림 막대 — 나머지가 주 그림보다 커지지 않게).
      → { placed, slots: [{key, x, y, w, h}], w, h, t } 또는 null */
  function shelves(groups, W, H, same, bare, hi) {
    var list = (groups || []).filter(function (g) { return g.units && g.units.length; });
    if (!list.length) { return { placed: [], slots: [], w: 0, h: 0, t: 0 }; }
    var all = [];
    list.forEach(function (g) { all = all.concat(g.units); });
    function lay(v) {
      var y = 0, out = [], slots = [], wMax = 0, over = false;
      list.forEach(function (g, gi) {
        if (gi) { y += GAP; }
        var top = y, x = 0, rowH = 0, slotW = 0;
        if (!bare) { y += HEAD; }
        g.units.forEach(function (u) {
          var bl = block(u, v, same);
          if (bl.w > W) { over = true; }
          if (x > 0 && x + GAP + bl.w > W) { y += rowH + GAP; x = 0; rowH = 0; }
          var x0 = x ? x + GAP : 0;
          for (var k = 0, mx = x0; k < u.members.length; mx += bl.ws[k] + GAP, k++) {
            out.push({ id: u.members[k].id, x: mx, y: y + bl.h - bl.hs[k], w: bl.ws[k], h: bl.hs[k], sc: bl.sc });
          }
          x = x0 + bl.w;
          rowH = Math.max(rowH, bl.h);
          slotW = Math.max(slotW, x);
        });
        y += rowH;
        slots.push({ key: g.key, x: 0, y: top, w: slotW, h: y - top });
        wMax = Math.max(wMax, slotW);
      });
      return { placed: out, slots: slots, w: wMax, h: y, over: over };
    }
    var cap = hi > 0 ? Math.min(hi, tCap(all, same)) : tCap(all, same);
    var t = search(cap, function (v) { var r = lay(v); return !r.over && r.h <= H; });
    if (!(t > 0)) { return null; }
    var res = lay(t);
    res.t = t;
    return res;
  }

  /** 칸 (x, y, w, h) 안에 장애물(고정 그림 · 잠긴 글자)이 있으면 그것을 뺀 빈 사각형(넓은 넷) 중 묶음이 가장 크게 들어가는 곳
      → { x, y, w, h }(장애물이 없으면 칸 그대로). v2-layout 큰 그림 칸 — 틀 전체를 빈 사각형 하나로 옮기면 그림이 다 작아졌다. */
  function room(x, y, w, h, obstacles, groups, same) {
    var box = { x: x, y: y, w: w, h: h }, top = null, P = window.FomsPartPack;
    var obs = (obstacles || []).filter(function (b) { return b.x < x + w && x < b.x + b.w && b.y < y + h && y < b.y + b.h; });
    if (!obs.length || !P) { return box; }
    P.freeRects({ x0: x, y0: y, x1: x + w, y1: y + h }, obs, GAP).sort(function (a, b) { return b.w * b.h - a.w * a.h; })
      .slice(0, 4).forEach(function (f) {
        var t = groups.length ? (shelves(groups, f.w, f.h, same) || { t: 0 }).t : f.w * f.h;
        if (!top || t > top.t) { top = { t: t, room: f }; }
      });
    return top ? top.room : box;
  }

  /** 그림을 r 줄로 — 순서대로 두고 줄 폭(같은 배율이면 원본 폭, 아니면 가로세로 비)을 고르게 끊는다. → [{ members }] 줄마다 한 묶음 */
  function rows(items, r, same) {
    var list = asUnits(items), wOf = function (u) { return u.members.reduce(function (s, m) { return s + (same ? m.nw : m.nw / m.nh); }, 0); };
    var total = list.reduce(function (s, u) { return s + wOf(u); }, 0), out = [], cur = [], acc = 0;
    list.forEach(function (u) {
      var w = wOf(u);
      if (cur.length && out.length < r - 1 && acc + w / 2 > total * (out.length + 1) / r) { out.push({ members: cur }); cur = []; }
      cur = cur.concat(u.members);
      acc += w;
    });
    if (cur.length) { out.push({ members: cur }); }
    return out;
  }

  /** 틀을 잴 칸(꼴 { x0, y0, x1, y1 }) — 종이 칸 그대로 + 장애물이 있으면 그것을 뺀 빈 사각형 중 넓은 셋. 종이 칸에서 잰 틀은
      장애물에 닿지 않을 때만 남는다(hits) — 큰 그림 칸이 고정 그림을 비켜 가면(room) 틀을 통째로 옮기지 않아도 된다. */
  function areas(full, obs) {
    if (!obs.length || !window.FomsPartPack) { return [full]; }
    return [full].concat(window.FomsPartPack.freeRects(full, obs, GAP).map(function (f) { return { x0: f.x, y0: f.y, x1: f.x + f.w, y1: f.y + f.h }; })
      .filter(function (a) { return a.x0 !== full.x0 || a.y0 !== full.y0 || a.x1 !== full.x1 || a.y1 !== full.y1; })
      .sort(function (a, b) { return (b.x1 - b.x0) * (b.y1 - b.y0) - (a.x1 - a.x0) * (a.y1 - a.y0); }).slice(0, 3));
  }
  function hits(r, obs) {
    return obs.some(function (b) { return r.moves.some(function (m) { return m.x < b.x + b.w && b.x < m.x + m.w && m.y < b.y + b.h && b.y < m.y + m.h; }); });
  }

  /** 글자 상자를 왼쪽부터 줄 바꿈 흐름으로(특이 사항 딱지). boxes = [{id, w, h}] → { placed, w, h } */
  function flow(boxes, W, gap) {
    var g = gap > 0 ? gap : 8, x = 0, y = 0, rowH = 0, w = 0, out = [];
    (boxes || []).forEach(function (b) {
      if (x > 0 && x + b.w > W) { y += rowH + g; x = 0; rowH = 0; }
      out.push({ id: b.id, x: x, y: y, w: b.w, h: b.h });
      x += b.w + g;
      rowH = Math.max(rowH, b.h);
      w = Math.max(w, x - g);
    });
    return { placed: out, w: w, h: out.length ? y + rowH : 0 };
  }

  window.FomsV2Pack = { GAP: GAP, HEAD: HEAD, MAX_UP: MAX_UP, row: row, stack: stack, shelves: shelves, flow: flow,
    unitH: unitH, room: room, block: block, search: search, tCap: tCap, rows: rows, areas: areas, hits: hits };
})();
