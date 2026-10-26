/**
 * 도면 마법사 V2 — 칸 안에 그림 · 글자를 늘어놓는 계산 도구(순수 계산).
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §4
 * - 그림 크기: sameScale(기본) = 한 칸 그림은 같은 배율(1000 폭 모듈과 500 폭 모듈이 반 크기로) · 아니면 같은 높이.
 *   어느 쪽이든 원본의 MAX_UP(1.25)배까지만 키운다(V1 part-layout.js 와 같음).
 * - 짝(내부 · 도어)은 한 묶음으로 옆에 붙인다(묶음 안 간격 GAP).
 *
 * window.FomsV2Pack = { GAP, HEAD, MAX_UP, row(items, maxW, maxH, same), stack(items, maxW, maxH, same),
 *   shelves(groups, W, H, same), flow(boxes, W, gap) }
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
      모든 칸이 같은 t(배율 · 높이)를 쓴다. → { placed, slots: [{key, x, y, w, h}], w, h, t } 또는 null */
  function shelves(groups, W, H, same) {
    var list = (groups || []).filter(function (g) { return g.units && g.units.length; });
    if (!list.length) { return { placed: [], slots: [], w: 0, h: 0, t: 0 }; }
    var all = [];
    list.forEach(function (g) { all = all.concat(g.units); });
    function lay(v) {
      var y = 0, out = [], slots = [], wMax = 0, over = false;
      list.forEach(function (g, gi) {
        if (gi) { y += GAP; }
        var top = y, x = 0, rowH = 0, slotW = 0;
        y += HEAD;
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
    var t = search(tCap(all, same), function (v) { var r = lay(v); return !r.over && r.h <= H; });
    if (!(t > 0)) { return null; }
    var res = lay(t);
    res.t = t;
    return res;
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
    unitH: unitH };
})();
