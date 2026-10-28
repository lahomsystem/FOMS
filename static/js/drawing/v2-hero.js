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
 *   주 그림이 GAIN 배 넘게 커질 때만 바꾼다 — 조금 커지려고 칸 모양을 바꾸지 않는다. 시트 스타일이 '고르게'(o.hero === false)면
 *   바꾸지 않고 키운 모습을 res.alt 에 남기고, 키웠으면 고르게 모습을 res.alt 에 남긴다(오른쪽 칸 스타일 고르기 미리보기 — v2-right.js).
 * - 주 그림 막대(사용자 요청 2026-10-28 '컴퍼넌트 사이즈는 자유로 조절 가능하게' — 숫자 읽힘 기준 대신): 폼 v2_hero_size(%)가 있으면
 *   주 그림을 고르게 때 높이의 그 %로(100% ~ 칸이 허락하는 만큼, 나머지 t ≥ 주 그림 t × RMIN · 주 그림보다 크지 않게) — 숫자 기준 ·
 *   두드러짐(LEAD) · GAIN 없이. res.size = { min: 100, max, pct, manual } 는 막대 범위와 지금 값(v2-size.js).
 *
 * window.FomsV2Hero = { pack(groups, W, H, same, opts) → { placed, slots, w, h, t, hero: [id] } | null,
 *   refine(res, inp, o, kit) → res(+ alt: { style: 'hero'|'even', slots, mainPct }, size), LEAD, RATIO, GAIN, RMIN }
 *   opts = { minH: { id: 이보다 작게 줄이지 않는 높이 }, ratio: 나머지 t ÷ 주 그림 t 아래 한계(기본 RATIO), free: 두드러짐 안 따짐,
 *   goal: 주 그림 높이(px — 이보다 크게 놓지 않고 나머지는 주 그림보다 크지 않게) } · kit = { groups: 큰 그림 칸 묶음, score(res) }
 */
(function () {
  'use strict';
  if (window.FomsV2Hero) { return; }

  var LEAD = 1.3, RATIO = 0.5, GAIN = 1.15, RMIN = 0.2;

  function pk() { return window.FomsV2Pack; }
  function areaOf(u) { return u.members.reduce(function (s, m) { return s + m.nw * m.nh; }, 0); }

  function pack(groups, W, H, same, opts) {
    var o = opts || {}, P = pk(), GAP = P.GAP, HEAD = P.HEAD, list = (groups || []).filter(function (g) { return g.units && g.units.length; }), all = [];
    list.forEach(function (g) { g.units.forEach(function (u) { all.push({ g: g, u: u }); }); });
    if (all.length < 2) { return null; }
    var ranked = all.slice().sort(function (a, b) { return areaOf(b.u) - areaOf(a.u); }), hero = ranked[0];
    if (!o.free && areaOf(hero.u) < LEAD * areaOf(ranked[1].u)) { return null; }
    var single = list.length === 1;
    if (!single && hero.g.units.length > 1) { return null; }
    var rest = single ? [{ key: hero.g.key, units: hero.g.units.filter(function (u) { return u !== hero.u; }) }]
      : list.filter(function (g) { return g !== hero.g; });
    var minH = o.minH || {}, ratio = o.ratio > 0 ? o.ratio : RATIO, top = single ? HEAD : 0, heroHead = single ? 0 : HEAD, Hc = H - top;
    function fit(r, t) {
      return !!r && r.t >= ratio * t && r.placed.every(function (p) { return !(minH[p.id] > p.h); });
    }
    var ways = [
      function (t) {   // 주 그림 왼쪽 · 나머지 오른쪽
        var b = P.block(hero.u, t, same);
        if (heroHead + b.h > Hc || b.w + GAP >= W) { return null; }
        var r = P.shelves(rest, W - b.w - GAP, Hc, same, single, o.goal ? t : 0);
        return fit(r, t) ? { b: b, r: r, rx: b.w + GAP, ry: 0 } : null;
      },
      function (t) {   // 주 그림 위 · 나머지 아래
        var b = P.block(hero.u, t, same), hh = heroHead + b.h;
        if (b.w > W || hh + GAP >= Hc) { return null; }
        var r = P.shelves(rest, W, Hc - hh - GAP, same, single, o.goal ? t : 0);
        return fit(r, t) ? { b: b, r: r, rx: 0, ry: hh + GAP } : null;
      }
    ];
    var cap = P.tCap([hero.u], same), bestT = 0, pick = null;
    if (o.goal > 0) { cap = Math.min(cap, same ? o.goal / P.unitH(hero.u) : o.goal); }
    ways.forEach(function (way) {   // 막대 값에 둘 다 닿으면 나머지가 더 크게 나오는 쪽
      var t = P.search(cap, function (v) { return !!way(v); }), got = t > 0 ? way(t) : null;
      if (t > bestT || (o.goal && got && pick && t === bestT && got.r.t > pick.r.t)) { bestT = t; pick = got; }
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

  /** 묶음 id 들 가운데 가장 큰 높이 — list = [{ id, h }] 또는 { id: { h } }. */
  function tall(ids, list) {
    var arr = Array.isArray(list) ? list : Object.keys(list).map(function (k) { return list[k]; });
    return arr.reduce(function (h, p) { return ids.indexOf(p.id) >= 0 ? Math.max(h, p.h) : h; }, 0);
  }

  function refine(res, inp, o, kit) {
    var L = window.FomsV2Layout, B = res && res.big, base = inp.base || {}, hasBase = Object.keys(base).length > 0;
    if (!B) { return res; }
    var lim = o.minText > 0 ? o.minText : L.MIN_TEXT, ids = {}, cur = {}, minH = {}, keys = {}, gain = Infinity, same = o.sameScale !== false;
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
    var top = pack(kit.groups, B.w, B.h, same, { ratio: RMIN, free: true }), even = top ? tall(top.hero, cur) : 0;   // 막대 끝 — 숫자 기준 없이 가장 크게
    var max = even > 0 ? Math.floor(100 * tall(top.hero, top.placed) / even) : 0;
    var want = max > 100 && o.heroSize > 0 ? Math.min(max, Math.max(100, Math.round(o.heroSize))) : 0;
    res.size = max > 100 ? { min: 100, max: max, pct: 100, manual: want > 0 } : null;
    var bt = want ? pack(kit.groups, B.w, B.h, same, { ratio: RMIN, free: true, goal: even * want / 100 })
      : pack(kit.groups, B.w, B.h, same, { minH: minH });
    if (!bt) { return res; }
    bt.placed.forEach(function (p) { if (bt.hero.indexOf(p.id) >= 0 && cur[p.id]) { gain = Math.min(gain, p.h / cur[p.id].h); } });
    if (gain === Infinity || !(want || gain >= GAIN)) { return res; }   // 막대 값은 조금 커져도 따른다
    var grown = { hero: bt.hero, moves: res.moves.filter(function (m) { return !ids[m.id]; }).concat(bt.placed.map(function (p) {
      return { id: p.id, x: Math.round(B.x + p.x), y: Math.round(B.y + p.y), w: p.w, h: p.h };
    })), slots: res.slots.filter(function (s) { return !keys[s.key]; }).concat(bt.slots.map(function (s) {
      return { key: s.key, x: Math.round(B.x + s.x), y: Math.round(B.y + s.y), w: Math.round(s.w), h: Math.round(s.h) };
    })) };
    if (o.hero === false) {   // 고르게 — 키운 모습은 미리보기로만
      var look = kit.score(Object.assign({}, res, grown));
      res.alt = { style: 'hero', slots: look.slots, mainPct: look.mainPct };
      return res;
    }
    res.alt = { style: 'even', slots: res.slots, mainPct: res.mainPct };
    var size = res.size && Object.assign({}, res.size, { pct: Math.round(100 * gain) }), out = kit.score(Object.assign(res, grown));
    out.size = size;
    return out;
  }

  /** 틀 고르기 끝(v2-layout compute): 주 그림을 키우면 원래 틀(plain), 안 키우는 시트(고르게 · 두드러진 그림 없음)는 여백을 덜 남기는 틀(filled).
      미리보기(alt) · 막대 범위(size)는 원래 틀 값 — 주 그림 크게로 바꾸면 그 틀에서 키운다. */
  function choose(plain, filled, inp, o, kit) {
    var r = plain ? refine(plain, inp, o, kit) : null;
    if (r && (r.hero || !filled || filled === plain)) { return r; }
    var f = filled ? refine(filled, inp, o, kit) : null;
    if (!f || !r) { return f || r; }
    if (f.hero) { return r; }
    f.alt = r.alt;
    f.size = r.size;
    return f;
  }

  window.FomsV2Hero = { pack: pack, refine: refine, choose: choose, LEAD: LEAD, RATIO: RATIO, GAIN: GAIN, RMIN: RMIN };
})();
