/**
 * 도면 마법사 — 그림 종류에 맞춘 자동 배치(순수 계산, 화면을 건드리지 않는다).
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.2
 * - 큰 그림 줄: 정면(내부·도어) → 입체 → 미분류, 올린 순서를 지켜 같은 모듈의 내부·도어가 나란히 온다.
 * - 그 아래 평면·상판 줄(큰 그림 높이의 0.42), 맨 아래 서랍 단면·부품 상세·사진 줄(0.48).
 * - 같은 줄의 그림은 같은 높이로 맞춘다(같은 높이의 장이면 폭이 실제 비율대로 보인다).
 * - 자재표 글자 상자 같은 장애물은 건너뛴다. 큰 그림 높이는 다 들어가는 가장 큰 값을 이분 탐색으로 찾는다.
 *
 * window.FomsPartLayout = { arrange(items, area, obstacles) → { placed: [{id,x,y,w,h}], mainH, crowded } }
 *   items     : [{ id, nw, nh, label, order }]  (nw/nh = 원본 픽셀, order = 올린 순서)
 *   area      : { x0, y0, x1, y1 }               (스테이지 논리 좌표)
 *   obstacles : [{ x, y, w, h }]
 */
(function () {
  'use strict';
  if (window.FomsPartLayout) { return; }

  var GAP = 16;
  var MIN_H = 40;
  var MAX_H = 560;
  var CROWDED_H = 180;
  var BAND_SCALE = { main: 1, plan: 0.42, small: 0.48 };
  var VIEW_RANK = { '정면·내부': 0, '정면·도어': 0, '입체·내부': 1, '입체·도어': 1, '미분류': 2, '그림 아님': 3 };

  function bandOf(label) {
    if (label === '평면·상판') { return 'plan'; }
    if (label === '서랍 단면' || label === '부품 상세' || label === '사진') { return 'small'; }
    return 'main';
  }

  function overlaps(a, b) {
    return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  }

  function firstHit(rect, obstacles) {
    for (var k = 0; k < obstacles.length; k++) {
      if (overlaps(rect, obstacles[k])) { return obstacles[k]; }
    }
    return null;
  }

  /** 띠(band)마다 줄을 왼쪽부터 채운다. 아래로 넘치면 null. */
  function pack(groups, area, obstacles, mainH) {
    var placed = [];
    var y = area.y0;
    var width = area.x1 - area.x0;
    for (var g = 0; g < groups.length; g++) {
      var list = groups[g].items;
      if (!list.length) { continue; }
      var h = Math.max(1, Math.round(mainH * BAND_SCALE[groups[g].band]));
      var x = area.x0;
      for (var i = 0; i < list.length; i++) {
        var it = list[i];
        var w = Math.max(1, Math.round(h * it.nw / it.nh));
        var hh = h;
        if (w > width) { w = width; hh = Math.max(1, Math.round(w * it.nh / it.nw)); }
        for (var guard = 0; guard < 200; guard++) {
          if (x + w > area.x1 && x > area.x0) { x = area.x0; y += h + GAP; }
          var hit = firstHit({ x: x, y: y, w: w, h: hh }, obstacles);
          if (!hit) { break; }
          x = hit.x + hit.w + GAP;
          if (x + w > area.x1) { x = area.x0; y += h + GAP; }
        }
        if (y + hh > area.y1) { return null; }
        placed.push({ id: it.id, x: Math.round(x), y: Math.round(y), w: w, h: hh });
        x += w + GAP;
      }
      y += h + GAP;
    }
    return placed;
  }

  function groupItems(items) {
    var ordered = items.filter(function (it) { return it.nw > 0 && it.nh > 0; })
      .slice().sort(function (a, b) { return a.order - b.order; });
    var main = ordered.filter(function (it) { return bandOf(it.label) === 'main'; });
    main.sort(function (a, b) {
      var ra = VIEW_RANK[a.label] == null ? 2 : VIEW_RANK[a.label];
      var rb = VIEW_RANK[b.label] == null ? 2 : VIEW_RANK[b.label];
      return (ra - rb) || (a.order - b.order);
    });
    var small = ordered.filter(function (it) { return bandOf(it.label) === 'small'; });
    small.sort(function (a, b) {
      return ((a.label === '사진') - (b.label === '사진')) || (a.order - b.order);
    });
    return [
      { band: 'main', items: main },
      { band: 'plan', items: ordered.filter(function (it) { return bandOf(it.label) === 'plan'; }) },
      { band: 'small', items: small }
    ];
  }

  /** 맨 위 얇은 띠(자재표 머리글 줄 같은 것)가 있으면 그 아래에서 시작하는 판도 만들어 둘 중 큰 쪽을 고른다. */
  function arrange(items, area, obstacles) {
    var obs = obstacles || [];
    var best = arrangeIn(items, area, obs);
    var top = area.y0, rest = [];
    obs.forEach(function (o) {
      if (o.y <= area.y0 + 120 && o.y + o.h <= area.y0 + 200) { top = Math.max(top, o.y + o.h + GAP); }
      else { rest.push(o); }
    });
    if (top > area.y0) {
      var lifted = arrangeIn(items, { x0: area.x0, y0: top, x1: area.x1, y1: area.y1 }, rest);
      if (lifted.mainH > best.mainH) { best = lifted; }
    }
    return best;
  }

  function arrangeIn(items, area, obs) {
    var groups = groupItems(items || []);
    // 작은 원본을 크게 늘려 흐려지지 않게: 큰 그림 높이는 원본 높이의 1.5배까지만
    var tallest = 0;
    groups.forEach(function (g) {
      g.items.forEach(function (it) { tallest = Math.max(tallest, it.nh / BAND_SCALE[g.band]); });
    });
    var lo = MIN_H, hi = Math.max(MIN_H, Math.min(MAX_H, tallest * 1.5));
    var best = pack(groups, area, obs, hi);
    var bestH = hi;
    if (!best) {
      best = null; bestH = 0;
      for (var iter = 0; iter < 18; iter++) {
        var mid = (lo + hi) / 2;
        var p = pack(groups, area, obs, mid);
        if (p) { best = p; bestH = mid; lo = mid; } else { hi = mid; }
      }
    }
    if (!best) {   // 장애물 때문에 하나도 못 놓으면 장애물을 무시하고 가장 작게
      best = pack(groups, area, [], MIN_H) || [];
      bestH = MIN_H;
    }
    return { placed: best, mainH: Math.round(bestH), crowded: bestH < CROWDED_H };
  }

  window.FomsPartLayout = { arrange: arrange, bandOf: bandOf };
})();
