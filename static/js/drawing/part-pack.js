/**
 * 도면 마법사 — 자동 배치 자리 계산 도우미(순수 계산, 화면을 건드리지 않는다).
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.2
 * - 줄(선반) 놓기: 모듈 묶음을 왼쪽부터 놓고, 묶음은 줄을 넘겨 가르지 않는다. 장애물(자재표 자리 등)은 그 줄에서 비켜 간다.
 * - 빈 사각형 목록: 놓인 그림·장애물을 뺀 빈 칸을 겹치는 큰 사각형들로 들고 있다가 남은 그림을 그 안에 넣는다.
 *
 * window.FomsPartPack = { hit, segments, shelves, maxScale, freeRects, cut, pick }
 *   사각형은 모두 { x, y, w, h }(스테이지 논리 좌표), 칸(area)은 { x0, y0, x1, y1 }.
 */
(function () {
  'use strict';
  if (window.FomsPartPack) { return; }

  var MIN_FREE = 8;   // 이보다 얇은 빈 칸은 버린다

  function hit(a, b) {
    return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  }

  /** 가로 띠 [y, y+h] 에서 장애물을 뺀 빈 구간 [[x0, x1], …] (왼쪽부터). */
  function segments(area, y, h, obstacles) {
    var segs = [[area.x0, area.x1]];
    obstacles.forEach(function (o) {
      if (!(o.y < y + h && y < o.y + o.h)) { return; }
      var next = [];
      segs.forEach(function (s) {
        if (o.x >= s[1] || o.x + o.w <= s[0]) { next.push(s); return; }
        if (o.x > s[0]) { next.push([s[0], o.x]); }
        if (o.x + o.w < s[1]) { next.push([o.x + o.w, s[1]]); }
      });
      segs = next;
    });
    return segs;
  }

  /** 줄마다 그 줄에서 가장 높은 그림 높이로 줄이고, 장애물에 안 걸리면 윗줄 바로 아래로 당긴다(그림은 줄 바닥에 맞춤). */
  function compact(bands, obstacles, gap) {
    var prev = null;
    bands.forEach(function (b) {
      var hk = 0, y = b.y;
      b.items.forEach(function (p) { hk = Math.max(hk, p.h); });
      if (prev != null && prev + gap < y) {
        var ny = prev + gap;
        var free = b.items.every(function (p) {
          var r = { x: p.x, y: ny + hk - p.h, w: p.w, h: p.h };
          return !obstacles.some(function (o) { return hit(r, o); });
        });
        if (free) { y = ny; }
      }
      b.items.forEach(function (p) { p.y = Math.round(y + hk - p.h); });
      b.y = Math.round(y); b.h = hk;
      prev = b.y + hk;
      delete b.items;
    });
    return prev;
  }

  /**
   * 모듈 묶음을 같은 픽셀 배율 s 로 줄마다 왼쪽부터 놓는다. 자리 찾기는 가장 높은 그림 높이의 띠로 하고,
   * 다 놓은 뒤 줄마다 제 높이로 줄여 위로 당긴다. 그림은 줄 바닥에 맞춘다.
   * units: [{ members: [{ id, nw, nh }] }] (놓는 순서대로). gap: 짝 안 간격, 묶음 사이는 그 두 배.
   * 반환 { placed: [{id,x,y,w,h}], rowH, bottom, bands: 줄마다 그림이 차지한 띠 [{x,y,w,h}], rest: [] } 또는 null(칸 아래로 넘침).
   * spill 이면 넘치는 묶음부터 끝까지를 rest 로 돌려준다(남은 빈 칸에 같은 배율로 놓으라고) — 하나도 못 놓으면 null.
   */
  function shelves(units, s, area, obstacles, y0, gap, spill) {
    var rowH = 0;
    units.forEach(function (u) {
      u.members.forEach(function (m) { rowH = Math.max(rowH, Math.max(1, Math.round(m.nh * s))); });
    });
    var placed = [], bands = [], rest = [], y = y0, segs = segments(area, y, rowH, obstacles), si = 0;
    var x = segs.length ? segs[0][0] : area.x0;
    for (var k = 0; k < units.length; k++) {
      var ws = units[k].members.map(function (m) { return Math.max(1, Math.round(m.nw * s)); });
      var uw = ws.reduce(function (a, b) { return a + b; }, 0) + gap * (ws.length - 1);
      for (var guard = 0; ; guard++) {
        if (y + rowH > area.y1 || guard > 60) {
          if (!spill || !k) { return null; }
          rest = units.slice(k);
          break;
        }
        while (si < segs.length && x + uw > segs[si][1]) {
          si++;
          if (si < segs.length) { x = Math.max(x, segs[si][0]); }
        }
        if (si < segs.length) { break; }
        y += rowH + gap;   // 다음 줄
        segs = segments(area, y, rowH, obstacles); si = 0;
        x = segs.length ? segs[0][0] : area.x0;
      }
      if (rest.length) { break; }
      var band = bands[bands.length - 1];
      if (!band || band.top !== y) { band = { x: Math.round(x), y: Math.round(y), top: y, w: 0, h: rowH, items: [] }; bands.push(band); }
      for (var i = 0; i < ws.length; i++) {
        var m = units[k].members[i], hh = Math.max(1, Math.round(m.nh * s));
        var p = { id: m.id, x: Math.round(x), y: Math.round(y + rowH - hh), w: ws[i], h: hh };
        placed.push(p); band.items.push(p);
        x += ws[i] + gap;
      }
      band.w = Math.round(x - gap) - band.x;
      x += gap;   // 모듈 사이는 짝 사이보다 조금 더 띄운다
    }
    var bottom = bands.length ? compact(bands, obstacles, gap) : y0;
    bands.forEach(function (b) { delete b.top; });
    return { placed: placed, rowH: rowH, bottom: bottom, bands: bands, rest: rest };
  }

  /** 묶음이 모두 줄에 들어가는 가장 큰 배율(hi 이하, 이분 탐색). 묶음이 없으면 hi, 하나도 안 되면 0. */
  function maxScale(units, area, obstacles, y0, gap, hi) {
    var fits = function (s) { return !!shelves(units, s, area, obstacles, y0, gap); };
    if (!units.length || fits(hi)) { return hi; }
    var lo = 0.004;
    if (!fits(lo)) { return 0; }
    for (var k = 0; k < 18; k++) { var mid = (lo + hi) / 2; if (fits(mid)) { lo = mid; } else { hi = mid; } }
    return lo;
  }

  /** 빈 사각형 목록에서 r 을 뺀다(최대 빈 사각형 방식). 얇은 칸·다른 칸 안에 든 칸은 버린다. */
  function cut(free, r) {
    var out = [];
    free.forEach(function (f) {
      if (!hit(f, r)) { out.push(f); return; }
      if (r.x > f.x) { out.push({ x: f.x, y: f.y, w: r.x - f.x, h: f.h }); }
      if (r.x + r.w < f.x + f.w) { out.push({ x: r.x + r.w, y: f.y, w: f.x + f.w - r.x - r.w, h: f.h }); }
      if (r.y > f.y) { out.push({ x: f.x, y: f.y, w: f.w, h: r.y - f.y }); }
      if (r.y + r.h < f.y + f.h) { out.push({ x: f.x, y: r.y + r.h, w: f.w, h: f.y + f.h - r.y - r.h }); }
    });
    out = out.filter(function (f) { return f.w > MIN_FREE && f.h > MIN_FREE; });
    return out.filter(function (f, i) {
      for (var j = 0; j < out.length; j++) {
        var g = out[j];
        if (j === i || g.x > f.x || g.y > f.y || g.x + g.w < f.x + f.w || g.y + g.h < f.y + f.h) { continue; }
        var same = g.x === f.x && g.y === f.y && g.w === f.w && g.h === f.h;
        if (!same || j < i) { return false; }   // 똑같은 칸은 앞의 것 하나만 남긴다
      }
      return true;
    });
  }

  /** 칸 전체에서 장애물·놓인 그림(pad 만큼 띄움)을 뺀 빈 사각형 목록. */
  function freeRects(area, blocks, pad) {
    var p = pad || 0;
    var free = [{ x: area.x0, y: area.y0, w: area.x1 - area.x0, h: area.y1 - area.y0 }];
    blocks.forEach(function (b) { free = cut(free, { x: b.x - p, y: b.y - p, w: b.w + 2 * p, h: b.h + 2 * p }); });
    return free;
  }

  /**
   * ww×hh 가 들어가는 빈 칸 하나를 고른다. 없으면 null.
   * mode 'left' = 가장 왼쪽(사진을 한쪽에 모음), 'fit' = 가장 꼭 맞는 칸(입체·평면), 'top' = 가장 위(작은 그림끼리).
   */
  function pick(free, ww, hh, mode) {
    var best = null, key = null;
    free.forEach(function (f) {
      if (f.w < ww || f.h < hh) { return; }
      var k = mode === 'left' ? [f.x, f.y] : (mode === 'fit' ? [f.w * f.h - ww * hh, f.y, f.x] : [f.y, f.x]);
      var better = !key;
      for (var i = 0; !better && i < k.length; i++) {
        if (k[i] < key[i]) { better = true; } else if (k[i] > key[i]) { break; }
      }
      if (better) { best = f; key = k; }   // 똑같으면 앞의 칸
    });
    return best ? { x: best.x, y: best.y, w: ww, h: hh } : null;
  }

  window.FomsPartPack = { hit: hit, segments: segments, shelves: shelves, maxScale: maxScale, freeRects: freeRects, cut: cut, pick: pick };
})();
