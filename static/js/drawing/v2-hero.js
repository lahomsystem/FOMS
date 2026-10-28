/**
 * 도면 마법사 V2 — 주 그림 크게(bento): 큰 그림 칸에서 원본 넓이가 두드러지게 큰 묶음 하나를 크게, 나머지는 남은 자리에
 * 같은 배율로(순수 계산).
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §4 — 사용자 요청 2026-10-28 '메인 컴퍼넌트를 크게(bento grid)'.
 *   스테이징 주문 4385: 같은 배율 한 줄은 폭에 막혀 주 그림이 501×362 · 칸 높이 515 중 150px 이 비었고, 손으로 키웠더니 옆 그림과 겹쳤다.
 * - pack: 주 그림 왼쪽 + 나머지 오른쪽, 주 그림 위 + 나머지 아래 중 주 그림이 크게 나오는 쪽(같으면 왼쪽).
 *   주 그림 = 원본 넓이가 둘째의 LEAD 배 넘는 묶음(비슷한 묶음끼리는 하나만 키우지 않는다). 나머지 t 는 주 그림 t 의 RATIO 배 이상
 *   (크기 차이 2배 안). 한 칸이면 머리 하나가 전체 위, 여러 칸(주방 정면 · 입체)이면 주 그림이 제 칸에 혼자일 때만 — 칸 머리는 칸마다.
 * - refine: v2-layout 이 틀을 고른 뒤(추천도 바꾸기 전 점수로) 큰 그림 칸(res.big — 장애물을 비켜 간 자리)을 다시 놓는다.
 *   나머지는 치수 글자 8px · 지금 양식 대비 60% 밑으로 줄이지 않고(이미 밑이면 지금보다 더 줄이지 않는다),
 *   주 그림이 GAIN 배 넘게 커질 때만 바꾼다 — 조금 커지려고 칸 모양을 바꾸지 않는다.
 *
 * window.FomsV2Hero = { pack(groups, W, H, same, opts) → { placed, slots, w, h, t, hero: [id] } | null,
 *   refine(res, inp, o, kit) → res, LEAD, RATIO, GAIN }
 *   opts.minH = { id: 이보다 작게 줄이지 않는 높이 } · kit = { groups: 큰 그림 칸 묶음, score(res) } (v2-layout 이 넘긴다)
 */
(function () {
  'use strict';
  if (window.FomsV2Hero) { return; }

  var LEAD = 1.3, RATIO = 0.5, GAIN = 1.15;

  function pk() { return window.FomsV2Pack; }
  function areaOf(u) { return u.members.reduce(function (s, m) { return s + m.nw * m.nh; }, 0); }

  function pack(groups, W, H, same, opts) {
    var P = pk(), GAP = P.GAP, HEAD = P.HEAD, list = (groups || []).filter(function (g) { return g.units && g.units.length; }), all = [];
    list.forEach(function (g) { g.units.forEach(function (u) { all.push({ g: g, u: u }); }); });
    if (all.length < 2) { return null; }
    var ranked = all.slice().sort(function (a, b) { return areaOf(b.u) - areaOf(a.u); }), hero = ranked[0];
    if (areaOf(hero.u) < LEAD * areaOf(ranked[1].u)) { return null; }
    var single = list.length === 1;
    if (!single && hero.g.units.length > 1) { return null; }
    var rest = single ? [{ key: hero.g.key, units: hero.g.units.filter(function (u) { return u !== hero.u; }) }]
      : list.filter(function (g) { return g !== hero.g; });
    var minH = (opts && opts.minH) || {}, top = single ? HEAD : 0, heroHead = single ? 0 : HEAD, Hc = H - top;
    function fit(r, t) {
      return !!r && r.t >= RATIO * t && r.placed.every(function (p) { return !(minH[p.id] > p.h); });
    }
    var ways = [
      function (t) {   // 주 그림 왼쪽 · 나머지 오른쪽
        var b = P.block(hero.u, t, same);
        if (heroHead + b.h > Hc || b.w + GAP >= W) { return null; }
        var r = P.shelves(rest, W - b.w - GAP, Hc, same, single);
        return fit(r, t) ? { b: b, r: r, rx: b.w + GAP, ry: 0 } : null;
      },
      function (t) {   // 주 그림 위 · 나머지 아래
        var b = P.block(hero.u, t, same), hh = heroHead + b.h;
        if (b.w > W || hh + GAP >= Hc) { return null; }
        var r = P.shelves(rest, W, Hc - hh - GAP, same, single);
        return fit(r, t) ? { b: b, r: r, rx: 0, ry: hh + GAP } : null;
      }
    ];
    var cap = P.tCap([hero.u], same), bestT = 0, pick = null;
    ways.forEach(function (way) {
      var t = P.search(cap, function (v) { return !!way(v); });
      if (t > bestT) { bestT = t; pick = way(t); }
    });
    if (!pick) { return null; }
    var out = [], b = pick.b, hy = top + heroHead, w = 0, h = 0;
    for (var k = 0, mx = 0; k < hero.u.members.length; mx += b.ws[k] + GAP, k++) {
      out.push({ id: hero.u.members[k].id, x: mx, y: hy + b.h - b.hs[k], w: b.ws[k], h: b.hs[k] });
    }
    pick.r.placed.forEach(function (p) { out.push({ id: p.id, x: p.x + pick.rx, y: p.y + top + pick.ry, w: p.w, h: p.h }); });
    out.forEach(function (p) { w = Math.max(w, p.x + p.w); h = Math.max(h, p.y + p.h); });
    var slots = single ? [{ key: hero.g.key, x: 0, y: 0, w: w, h: h }]
      : [{ key: hero.g.key, x: 0, y: 0, w: b.w, h: heroHead + b.h }].concat(pick.r.slots.map(function (s) {
        return { key: s.key, x: s.x + pick.rx, y: s.y + pick.ry, w: s.w, h: s.h };
      }));
    return { placed: out, slots: slots, w: w, h: h, t: bestT, hero: hero.u.members.map(function (m) { return m.id; }) };
  }

  function refine(res, inp, o, kit) {
    var L = window.FomsV2Layout, B = res && res.big, base = inp.base || {}, hasBase = Object.keys(base).length > 0;
    if (!B || o.hero === false) { return res; }
    var lim = o.minText > 0 ? o.minText : L.MIN_TEXT, ids = {}, cur = {}, minH = {}, keys = {}, gain = Infinity;
    kit.groups.forEach(function (g) {
      keys[g.key] = true;
      g.units.forEach(function (u) { u.members.forEach(function (m) { ids[m.id] = true; }); });
    });
    res.moves.forEach(function (m) { if (ids[m.id]) { cur[m.id] = m; } });
    Object.keys(cur).forEach(function (id) {
      var it = inp.byId[id], floor = 0;
      if (it && it.tx > 0 && it.nh > 0) { floor = lim * it.nh / it.tx; }
      if (hasBase && base[id] && base[id].h > 0) { floor = Math.max(floor, L.CROWD_PCT * base[id].h); }
      minH[id] = Math.min(floor, cur[id].h);
    });
    var bt = pack(kit.groups, B.w, B.h, o.sameScale !== false, { minH: minH });
    if (!bt) { return res; }
    bt.placed.forEach(function (p) { if (bt.hero.indexOf(p.id) >= 0 && cur[p.id]) { gain = Math.min(gain, p.h / cur[p.id].h); } });
    if (gain === Infinity || !(gain >= GAIN)) { return res; }
    res.moves = res.moves.filter(function (m) { return !ids[m.id]; }).concat(bt.placed.map(function (p) {
      return { id: p.id, x: Math.round(B.x + p.x), y: Math.round(B.y + p.y), w: p.w, h: p.h };
    }));
    res.slots = res.slots.filter(function (s) { return !keys[s.key]; }).concat(bt.slots.map(function (s) {
      return { key: s.key, x: Math.round(B.x + s.x), y: Math.round(B.y + s.y), w: Math.round(s.w), h: Math.round(s.h) };
    }));
    res.hero = bt.hero;
    return kit.score(res);
  }

  window.FomsV2Hero = { pack: pack, refine: refine, LEAD: LEAD, RATIO: RATIO, GAIN: GAIN };
})();
