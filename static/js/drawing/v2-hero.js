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
 *   빈자리를 채운 틀(v2-fill)은 옮긴 칸(평면 · 상세)을 빼고 키운 뒤 남은 빈자리에 다시 옮겨 넣는다(못 넣으면 안 키운다).
 * - 틀 견주기(heroPick — 2026-10-29 스테이징 4385 · 4465 를 그림 빼고 더해 66가지로 실화면 조사): 고른 틀 하나만 키우면 큰 그림 칸
 *   모양이 주 그림과 안 맞아 오른쪽 기둥이 통째로 비었다(빈칸 16~21%). 옮긴 칸 묶음마다 점수 높은 틀 PER 개에서도 키워 보고,
 *   치수 글자 8px → 사진(200px 까지) · 가장 작은 그림(DROP 넘게 줄이지 않음) · 상세 · 평면이 주 그림보다 크지 않음을 지키며 점수가 높은 모습.
 *   키운 모습이 치수 글자 8px 를 못 지키는데 고르게는 지키면 키우지 않는다(띠형에서 사진 114px · 치수 글자 4px 이 됐다).
 * - 주 그림 막대(사용자 요청 2026-10-28 '컴퍼넌트 사이즈는 자유로 조절 가능하게' — 숫자 읽힘 기준 대신): 폼 v2_hero_size(%)가 있으면
 *   주 그림을 고르게 때 높이의 그 %로(100% ~ 칸이 허락하는 만큼, 나머지 t ≥ 주 그림 t × RMIN · 주 그림보다 크지 않게) — 숫자 기준 ·
 *   두드러짐(LEAD) · GAIN 없이. res.size = { min: 100, max, pct, manual } 는 막대 범위와 지금 값(v2-size.js).
 *
 * window.FomsV2Hero = { pack(groups, W, H, same, opts) → { placed, slots, w, h, t, hero: [id] } | null,
 *   refine(res, inp, o, kit) → res(+ alt: { style: 'hero'|'even', slots, mainPct, 키운 모습 숫자 }, size),
 *   choose(plain, filled, inp, o, kit) → res, LEAD, RATIO, GAIN, RMIN }
 *   opts = { minH: { id: 이보다 작게 줄이지 않는 높이 }, ratio: 나머지 t ÷ 주 그림 t 아래 한계(기본 RATIO), free: 두드러짐 안 따짐,
 *   goal: 주 그림 높이(px — 이보다 크게 놓지 않고 나머지는 주 그림보다 크지 않게) }
 *   kit = { groups: 큰 그림 칸 묶음, score(res), cands: { band, column }(견줄 틀 — 점수 매긴 것) } · o.quick = 막대 범위 생략(틀 견주기)
 */
(function () {
  'use strict';
  if (window.FomsV2Hero) { return; }

  var LEAD = 1.3, RATIO = 0.5, GAIN = 1.15, RMIN = 0.2, PER = 5, DROP = 0.1, PHOTO_H = 200;   // PHOTO_H = v2-fill 사진 벌점 기준과 같다

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

  /** 빈자리를 채운 틀(v2-fill)에서 옮긴 칸(평면 · 상세)을 뺀 모습 — 주 그림을 키운 뒤 남은 빈자리에 다시 옮겨 넣는다. */
  function strip(res, inp) {
    var gone = {}, keys = {};
    res.fillKeys.forEach(function (k) { keys[k] = true; (inp[k] || []).forEach(function (it) { gone[it.id] = true; }); });
    return Object.assign({}, res, { moves: res.moves.filter(function (m) { return !gone[m.id]; }),
      slots: res.slots.filter(function (s) { return !keys[s.key]; }) });
  }

  function refine(res, inp, o, kit, ref) {
    var L = window.FomsV2Layout, B = res && res.big, base = inp.base || {}, hasBase = Object.keys(base).length > 0;
    if (!B) { return res; }
    var mv = res.fillKeys && res.fillKeys.length ? res.fillKeys : null, work = mv ? strip(res, inp) : res;
    var lim = o.minText > 0 ? o.minText : L.MIN_TEXT, ids = {}, cur = {}, minH = {}, keys = {}, gain = Infinity, same = o.sameScale !== false;
    kit.groups.forEach(function (g) {
      keys[g.key] = true;
      g.units.forEach(function (u) { u.members.forEach(function (m) { ids[m.id] = true; }); });
    });
    work.moves.forEach(function (m) { if (ids[m.id]) { cur[m.id] = m; } });
    Object.keys(cur).forEach(function (id) {
      var it = inp.byId[id], floor = 0;
      if (it && it.tx > 0 && it.nh > 0) { floor = lim * it.nh / it.tx; }
      if (hasBase && base[id] && base[id].h > 0) { floor = Math.max(floor, L.CROWD_PCT * base[id].h); }
      minH[id] = Math.min(floor, cur[id].h);
    });
    var top = o.quick ? null : pack(kit.groups, B.w, B.h, same, { ratio: RMIN, free: true });   // 막대 끝 — 숫자 기준 없이 가장 크게
    var even = top ? tall(top.hero, ref ? ref.moves : cur) || tall(top.hero, cur) : 0;   // 막대 100% = 고르게로 놓일 틀(ref — 빈자리 채우기)의 주 그림
    var max = even > 0 ? Math.floor(100 * tall(top.hero, top.placed) / even) : 0;
    var want = max > 100 && o.heroSize > 0 ? Math.min(max, Math.max(100, Math.round(o.heroSize))) : 0;
    res.size = max > 100 ? { min: 100, max: max, pct: 100, manual: want > 0 } : null;
    var bt = want ? pack(kit.groups, B.w, B.h, same, { ratio: RMIN, free: true, goal: even * want / 100 })
      : pack(kit.groups, B.w, B.h, same, { minH: minH });
    if (!bt) { return res; }
    bt.placed.forEach(function (p) { if (bt.hero.indexOf(p.id) >= 0 && cur[p.id]) { gain = Math.min(gain, p.h / cur[p.id].h); } });
    if (gain === Infinity || !(want || gain >= GAIN)) { return res; }   // 막대 값은 조금 커져도 따른다
    var grown = { hero: bt.hero, moves: work.moves.filter(function (m) { return !ids[m.id]; }).concat(bt.placed.map(function (p) {
      return { id: p.id, x: Math.round(B.x + p.x), y: Math.round(B.y + p.y), w: p.w, h: p.h };
    })), slots: work.slots.filter(function (s) { return !keys[s.key]; }).concat(bt.slots.map(function (s) {
      return { key: s.key, x: Math.round(B.x + s.x), y: Math.round(B.y + s.y), w: Math.round(s.w), h: Math.round(s.h) };
    })) };
    if (mv && !window.FomsV2Fill.place(grown, inp, mv, B, same, kit.groups)) { return res; }   // 옮긴 칸이 들어갈 빈자리가 없으면 안 키운다
    if (o.hero === false) {   // 고르게 — 키운 모습은 미리보기로만(숫자는 heroPick 이 틀을 견줄 때)
      var look = kit.score(Object.assign({}, res, grown));
      res.alt = { style: 'hero', slots: look.slots, mainPct: look.mainPct, minPct: look.minPct, minText: look.minText, score: look.score,
        photoH: photoOf(look, inp), smallMax: smallOf(look, inp) };
      return res;
    }
    res.alt = { style: 'even', slots: res.slots, mainPct: res.mainPct };
    var size = res.size && Object.assign({}, res.size, { pct: Math.round(100 * tall(bt.hero, bt.placed) / even) }), out = kit.score(Object.assign(res, grown));
    out.size = size;
    return out;
  }

  function photoOf(r, inp) {
    return r.moves.reduce(function (h, m) { var it = inp.byId[m.id]; return it && it.slot === 'photo' ? Math.min(h, m.h) : h; }, Infinity);
  }
  function smallOf(r, inp) {   // 상세 · 평면 가운데 가장 크게 놓인 % — 주 그림 % 보다 크면 비율이 이상하다
    return Object.keys(r.pct || {}).reduce(function (v, id) {
      var it = inp.byId[id];
      return it && (it.slot === 'detail' || it.slot === 'plan') ? Math.max(v, r.pct[id]) : v;
    }, 0);
  }
  /** 키운 모습 — 주 그림 크게면 결과 자체, 고르게면 미리보기(res.alt). */
  function lookOf(r, inp) {
    if (r && r.hero) { r.photoH = photoOf(r, inp); r.smallMax = smallOf(r, inp); return r; }
    return r && r.alt && r.alt.style === 'hero' ? r.alt : null;
  }
  function dupe(r) { return Object.assign({}, r, { moves: r.moves.slice(), slots: r.slots.slice() }); }
  function readable(x) { return !(x.minText != null && x.minText < window.FomsV2Layout.MIN_TEXT); }

  /** 키운 모습 l 이 tl 보다 나은가 — 치수 글자 8px 를 지키는 쪽이 먼저(둘 다 못 지키면 더 읽히는 쪽). 그다음은 사진(PHOTO_H 까지) ·
      가장 작은 그림을 DROP 넘게 줄이지 않고 상세 · 평면을 주 그림보다 크게 놓지 않으면서 점수(빈자리 · 사진 벌점 포함)가 높은 쪽. */
  function better(l, tl) {
    var okL = readable(l), okT = readable(tl), dMin = (l.minPct || 0) - (tl.minPct || 0);
    if (okL !== okT) { return okL; }
    if (!okL) { return l.minText > tl.minText + 0.5 && dMin >= -0.02; }
    if (l.photoH < Math.min(tl.photoH, PHOTO_H) - 2 || dMin < -DROP) { return false; }
    if (l.smallMax > Math.max(l.mainPct, tl.smallMax) + 0.01) { return false; }
    return l.score > tl.score + 0.02;
  }

  /** 고른 틀(plain)과 옮긴 칸 묶음마다 점수 높은 틀 PER 개에서 키워 보고 나은 모습(better). 고른 틀에서 못 키우거나 막대로 정했으면
      그대로. 키운 모습이 치수 글자 8px 를 못 지키는데 고르게는 지키면 안 키운다(막대 범위는 남긴다). 고르게 스타일은 틀을 그대로 두고
      미리보기 · 막대만 이긴 틀에서 — 두 스타일이 같은 모습을 본다. */
  function heroPick(plain, inp, o, kit, ref) {
    var top = refine(dupe(plain), inp, o, kit, ref), tl = lookOf(top, inp), win = plain, q = Object.assign({}, o, { quick: true }), seen = {};
    if (!tl || o.heroSize > 0) { return top; }
    ((kit.cands || {})[plain.template] || []).filter(Boolean).sort(function (a, b) { return b.score - a.score; }).forEach(function (c) {
      var k = (c.fillKeys || []).join('+');   // 묶음마다 PER 개 — 평면을 옮긴 틀만 몰려 상세를 옮긴 틀을 못 봤다
      seen[k] = (seen[k] || 0) + 1;
      if (c === plain || seen[k] > PER) { return; }
      var l = lookOf(refine(dupe(c), inp, q, kit, ref), inp);
      if (l && better(l, tl)) { win = c; tl = l; }
    });
    if (win !== plain) { top = refine(dupe(win), inp, o, kit, ref); }   // 이긴 틀만 막대 범위까지 다시
    var keep = !readable(tl) && readable(ref || plain);
    if (!keep && (o.hero !== false || win === plain)) { return top; }
    var r = dupe(plain);
    r.alt = keep ? null : top.alt;
    r.size = top.size;
    return r;
  }

  /** 틀 고르기 끝(v2-layout compute): 주 그림을 키우면 원래 틀(plain), 안 키우는 시트(고르게 · 두드러진 그림 없음)는 여백을 덜 남기는 틀(filled —
      상세 두 줄 · 빈자리 채우기 v2-fill). 미리보기(alt)는 두 스타일이 실제로 놓일 모습, 막대(size) 100% 는 고르게로 놓일 주 그림 높이. */
  function choose(plain, filled, inp, o, kit) {
    var ref = filled && filled !== plain ? filled : null, r = plain ? heroPick(plain, inp, o, kit, ref) : null;
    if (r && r.hero && ref) { r.alt = { style: 'even', slots: ref.slots, mainPct: ref.mainPct }; }
    if (r && (r.hero || !filled || filled === plain)) { return r; }
    var f = filled ? (filled.fillKeys ? filled : refine(filled, inp, o, kit)) : null;   // 빈자리 채운 틀은 heroPick 이 이미 견줬다
    if (!f || !r) { return f || r; }
    if (f.hero) { return r; }
    f.alt = r.alt;
    f.size = r.size;
    return f;
  }

  window.FomsV2Hero = { pack: pack, refine: refine, choose: choose, LEAD: LEAD, RATIO: RATIO, GAIN: GAIN, RMIN: RMIN };
})();
