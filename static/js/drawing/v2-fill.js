/**
 * 도면 마법사 V2 — 빈자리 채우기: 큰 그림 칸이 높이 · 폭에 막혀 남긴 빈 사각형에 작은 칸(평면 · 상세)을 옮겨 넣는다(순수 계산).
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §4 — 사용자 요청 2026-10-28 '여전히 공간을 비 효율적으로 써 —
 *   예시 처럼 공간을 꽉 채워 사용하도록 해(비율이 아주 이상하지만 않게)' · '강조 문구를 넣으면 아래 전체 공백이 생겨'.
 *   스테이징 주문 4385(왼쪽 기둥형): 큰 그림 칸(정면 둘 · 입체)이 높이에 막혀 폭 826 중 636만 쓰고 오른쪽 190px 기둥이 통째로 비었고,
 *   평면은 왼쪽 기둥에 끼어 상세가 62%로 작아졌다.
 * - v2-layout 이 틀마다 옮길 칸(없음 · 평면 · 상세 · 둘 다 — subsets)을 재 본다. 옮긴 칸은 띠 · 기둥에서 빠져 남은 칸이 커지고,
 *   큰 그림 칸의 빈 사각형(놓인 그림 · 글자 · 칸 머리 · 장애물을 GAP 띄워 뺀 것) 가운데 가장 크게 들어가는 곳 왼쪽 위에 놓인다.
 *   띠형은 종이 칸 전체에서 찾는다(2026-10-29 — 위 띠 자재 · 특이 밑이 비었다: 스테이징 4385 띠형 빈칸 17% → 5%, 사진 258 → 344px).
 *   점수(가장 작은 그림 % 중심)가 나은 틀이 이긴다 — 옮겨서 그림이 더 작아지면 옮기지 않는다.
 * - 옮긴 칸은 큰 그림보다 큰 배율로 놓지 않는다(같은 배율이면 t ≤ 큰 그림 t, 아니면 높이 ≤ 큰 그림 높이) — 비율이 이상하지 않게.
 *   칸 머리 최소 폭(HEAD_MIN_W)보다 좁은 빈 사각형은 쓰지 않는다.
 *
 * window.FomsV2Fill = { subsets(keys) → [[key]](빈 묶음 먼저), place(res, inp, keys, room, same, groups) → boolean }
 *   room = 찾을 칸 { x, y, w, h }(기둥형 = 큰 그림 칸, 띠형 = 종이 칸) · groups = 큰 그림 칸 묶음(v2-layout bigGroups) · 성공하면 res.fillKeys · fillRoom
 */
(function () {
  'use strict';
  if (window.FomsV2Fill) { return; }

  var BLANK_W = 1, PHOTO_H = 200, PHOTO_W = 0.5;

  function subsets(keys) {
    var out = [[]];
    (keys || []).forEach(function (k) { out = out.concat(out.map(function (s) { return s.concat([k]); })); });
    return out;
  }

  function hit(a, b) { return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h; }

  /** 큰 그림 칸 안 막힌 자리 — 놓인 그림 · 칸 머리(최소 폭) · 장애물. */
  function blocks(res, inp, room, headW) {
    var HEAD = window.FomsV2Pack.HEAD, out = [];
    res.moves.forEach(function (m) { if (hit(m, room)) { out.push(m); } });   // 그림 · 글자(자재 · 특이 · 강조 — 띠형은 종이 칸 전체에서 찾는다)
    res.slots.forEach(function (s) { if (hit(s, room)) { out.push({ x: s.x, y: s.y, w: Math.max(s.w, headW), h: HEAD }); } });
    (inp.obstacles || []).forEach(function (b) { if (hit(b, room)) { out.push(b); } });
    return out;
  }

  function areaOf(list) { return list.reduce(function (s, it) { return s + it.nw * it.nh; }, 0); }

  function place(res, inp, keys, room, same, groups) {
    var P = window.FomsV2Pack, PP = window.FomsPartPack, headW = window.FomsV2Layout.HEAD_MIN_W, big = {}, hi = same ? Infinity : 0;
    if (!keys || !keys.length) { return true; }
    if (!PP || !room) { return false; }
    (groups || []).forEach(function (g) { g.units.forEach(function (u) { u.members.forEach(function (m) { big[m.id] = true; }); }); });
    res.moves.forEach(function (m) {
      var it = inp.byId[m.id];
      if (big[m.id] && it && it.nh > 0) { hi = same ? Math.min(hi, m.h / it.nh) : Math.max(hi, m.h); }
    });
    if (!(hi > 0 && hi < Infinity)) { return false; }   // 큰 그림이 없으면 옮겨 넣을 칸도 없다
    var area = { x0: room.x, y0: room.y, x1: room.x + room.w, y1: room.y + room.h }, used = blocks(res, inp, room, headW);
    var order = keys.slice().sort(function (a, b) { return areaOf(inp[b]) - areaOf(inp[a]); });   // 큰 칸부터
    var ok = order.every(function (key) {
      var grp = [{ key: key, units: inp[key].map(function (it) { return { members: [it] }; }) }], top = null;
      PP.freeRects(area, used, P.GAP).forEach(function (f) {
        if (f.w < headW) { return; }
        var sh = P.shelves(grp, f.w, f.h, same, false, hi);
        if (sh && sh.placed.length && (!top || sh.t > top.sh.t)) { top = { sh: sh, f: f }; }
      });
      if (!top) { return false; }
      top.sh.placed.forEach(function (p) {
        res.moves.push({ id: p.id, x: Math.round(top.f.x + p.x), y: Math.round(top.f.y + p.y), w: p.w, h: p.h });
      });
      top.sh.slots.forEach(function (s) {
        var b = { key: s.key, x: Math.round(top.f.x + s.x), y: Math.round(top.f.y + s.y), w: Math.round(s.w), h: Math.round(s.h) };
        res.slots.push(b);
        used.push({ x: b.x, y: b.y, w: Math.max(b.w, headW), h: b.h });
      });
      return true;
    });
    if (ok) { res.fillKeys = keys.slice(); res.fillRoom = room; }
    return ok;
  }

  /** 가장 큰 빈 사각형 넓이 ÷ 종이 칸 넓이(0~1) — 틀 점수 벌점(v2-layout score). 그림 · 글자 · 칸 머리 · 장애물(고정 그림 · 남는 메모)을
      GAP 절반씩 띄워 뺀다. */
  function blank(res, area, obstacles) {
    var PP = window.FomsPartPack, P = window.FomsV2Pack, used = res.moves.concat(obstacles || []), top = 0;
    if (!PP) { return 0; }
    res.slots.forEach(function (s) { used.push({ x: s.x, y: s.y, w: s.w, h: P.HEAD }); });
    PP.freeRects(area, used, P.GAP / 2).forEach(function (f) { top = Math.max(top, f.w * f.h); });
    return top / ((area.x1 - area.x0) * (area.y1 - area.y0));
  }

  /** 틀 점수 벌점(v2-layout score — 고르게 쪽 틀만): 가장 큰 빈 사각형(res.blank) × BLANK_W + 사진이 PHOTO_H 보다 낮으면 모자란 만큼 ×
      PHOTO_W. 사진은 '가장 작은 그림'에서 빠져 빈자리 채우기가 기둥을 좁히며 사진을 160px 폭까지 줄였다. */
  function penalty(res, inp) {
    var photoH = Infinity;
    res.moves.forEach(function (m) { var it = inp.byId[m.id]; if (it && it.slot === 'photo') { photoH = Math.min(photoH, m.h); } });
    res.blank = blank(res, inp.full, inp.obstacles);
    return BLANK_W * res.blank + (photoH < PHOTO_H ? PHOTO_W * (1 - photoH / PHOTO_H) : 0);
  }

  window.FomsV2Fill = { subsets: subsets, place: place, blank: blank, penalty: penalty, BLANK_W: BLANK_W, PHOTO_H: PHOTO_H };
})();
