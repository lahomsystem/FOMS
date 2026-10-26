/**
 * 도면 마법사 — 그림 종류에 맞춘 자동 배치(순수 계산, 화면을 건드리지 않는다).
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.2
 * - 크기가 같은(가로·세로 2% 안) 두 장은 한 묶음: 내부 왼쪽·도어 오른쪽(정면 짝·입체 짝 모두, 묶음은 가르지 않는다).
 *   한쪽이 미분류여도, 도어를 '부품 상세'로 잘못 붙였어도 크기가 정면·입체 그림과 같으면 묶고 guess 에 짝 이름을 적는다.
 * - 큰 그림 줄은 모두 같은 픽셀 배율(1000 폭 모듈과 500 폭 모듈이 반 크기로 보이게), 그림마다 확대는 1.25배까지.
 *   줄에 다 안 들어가는 뒤쪽 묶음은 같은 배율 그대로 남은 빈 칸(자재표 왼쪽 등)에 놓아 본다.
 * - 남은 빈 칸에 입체 → 평면(줄 높이의 0.5~1.25) → 서랍·부품(0.35~0.6) → 사진(한쪽에 모음). 종류를 모르는 그림은
 *   줄 배율보다 크게 놓지 않는다. 남은 칸 그림은 먼저 치수 글자 9.5px 로 놓아 보고(안 되면 8px 까지, 그래도 안 되면 그
 *   그림들만 줄여 다시), 현장 사진('사진')은 높이 120px 밑으로 줄이지 않는다(못 지키면 crowded → 나누기 계획이 옮긴다).
 * - 후보(입체를 줄에 둘지 · 자재표 왼쪽부터/아래부터 · 줄 폭 · 배율) 중 점수(채운 넓이 + 큰 그림 줄 높이 − 가장 큰 빈 칸
 *   + 평면 크기 + 가장 작은 글자)가 가장 좋은 것. 치수 글자(tx, 원본 픽셀)가 화면에서 minText(8px) 밑이 되는 배치는
 *   고르지 않고, 그래도 다 안 들어가면 crowded=true 로 글자가 가장 큰 배치를 돌려준다(나누기 계획은 part-split.js).
 *
 * window.FomsPartLayout = { arrange(items, area, obstacles, opts) → result, groups(items), MIN_TEXT, PHOTO_MIN }
 *   items  : [{ id, nw, nh, label, order, tx }] (원본 픽셀 · 놓는 순서 · 치수 글자 높이, 0 = 모름)
 *   area   : { x0, y0, x1, y1 } (스테이지 논리 좌표) · obstacles : [{ x, y, w, h }] (띄움 포함)
 *   opts   : { reserve: {x,y,w,h} 자재표 자리, minText: 8, probe: true = 글자를 지키는 배치가 있는지만 빨리 }
 *   result : { placed: [{id,x,y,w,h}] (놓은 순서), scale, mainH, minText(px|null), crowded, guess: { id: 짝 이름표 },
 *              why: crowded 까닭('text' 글자 · 'photo' 사진만 · ''), photo: 가장 작은 사진 높이(px|null) }
 * 같은 입력이면 늘 같은 답(무작위 없음). part-pack.js 를 먼저 불러야 한다.
 */
(function () {
  'use strict';
  if (window.FomsPartLayout) { return; }

  var GAP = 16;
  var MAX_UP = 1.25;
  var MIN_TEXT = 8;
  var FALLBACK_H = 150;   // 글자 크기를 하나도 모를 때만: 큰 그림 줄이 이보다 낮으면 '너무 작음'
  var GOOD_TEXT = 9.5;    // 남은 칸 그림은 먼저 치수 글자가 이만큼 되게 놓아 본다(실화면 V3: 평면·입체가 8.2px 까지 내려갔다)
  var PHOTO_MIN = 120;    // 현장 사진 높이 하한(실화면 V3: 그림 15장 시트에서 63×84 우표만 해졌다)
  var STEPS = 8;          // 줄에 다 들어가는 가장 큰 배율에서 0.93배씩 줄여 보는 횟수
  var MAX_TRY = 22;       // 한 후보 틀에서 재 보는 배율 수 상한
  var WIDTHS = [1, 0.72, 0.55];        // 큰 그림 줄을 칸 폭의 이만큼까지만 — 좁히면 줄이 늘고 오른쪽에 평면·입체 자리가 생긴다
  var SHRINK = [1, 0.8, 0.64, 0.5];    // 남은 칸 그림이 다 안 들어가면 그 그림들만 이만큼 줄여 다시 놓아 본다
  var FRONT = { '정면·내부': 1, '정면·도어': 1 };
  var ISO = { '입체·내부': 1, '입체·도어': 1 };
  var RATIOS = {          // 큰 그림 줄 높이에 대한 비율(큰 것부터). tight = 글자를 못 지킬 때만 더 줄여 보는 값
    iso: [1, 0.9, 0.8, 0.7, 0.6, 0.5], plan: [1.25, 1.1, 1, 0.9, 0.8, 0.7, 0.6, 0.5], small: [0.6, 0.55, 0.5, 0.45, 0.4, 0.35],
    photo: [0.7, 0.6, 0.5, 0.45, 0.4, 0.35], tight: [0.3, 0.25, 0.2, 0.15, 0.1, 0.07]
  };
  var MODE = { iso: 'fit', plan: 'fit', small: 'top', photo: 'left', unit: 'fit' };

  function sameSize(a, b) {
    return Math.abs(a.nw - b.nw) <= 0.02 * Math.max(a.nw, b.nw) && Math.abs(a.nh - b.nh) <= 0.02 * Math.max(a.nh, b.nh);
  }
  function side(it) { return /내부$/.test(it.label) ? 0 : (/도어$/.test(it.label) ? 2 : 1); }   // 내부 · 모름 · 도어
  function flat(units) { return units.reduce(function (a, u) { return a.concat(u.members); }, []); }
  function pad(r, p) { return { x: r.x - p, y: r.y - p, w: r.w + 2 * p, h: r.h + 2 * p }; }
  function unitH(u) { return Math.max.apply(null, u.members.map(function (m) { return m.nh; })); }
  function one(it) { return { kind: it.kind, members: [it], order: it.order }; }

  /** 같은 크기 짝 묶기 — 올린 순서가 가장 가까운 것, 내부+내부·도어+도어는 짝이 아니다.
      부품·서랍으로 짐작했다가 짝으로 올린 그림(promoted)은 짝의 반대쪽 이름을 guess 에 적는다. */
  function pairUp(main, guess) {
    var used = {}, units = [];
    main.forEach(function (m, i) {
      if (used[i]) { return; }
      used[i] = true;
      var best = -1;
      main.forEach(function (p, j) {
        if (used[j] || p.kind !== m.kind || !sameSize(p, m)) { return; }
        if (side(m) !== 1 && side(m) === side(p)) { return; }
        if (best < 0 || Math.abs(p.order - m.order) < Math.abs(main[best].order - m.order)) { best = j; }
      });
      var members = [m], b = main[best];
      if (b) {
        used[best] = true;
        members = side(b) < side(m) ? [b, m] : [m, b];
        [[m, b], [b, m]].forEach(function (q) {
          if (q[0].promoted && side(q[1]) !== 1) {
            guess[q[0].id] = (q[0].kind === 'front' ? '정면·' : '입체·') + (side(q[1]) === 0 ? '도어' : '내부');
          }
        });
      }
      units.push({ kind: m.kind, members: members, order: m.order });
    });
    var rank = { front: 0, iso: 1, other: 2 };
    return units.sort(function (a, b) { return (rank[a.kind] - rank[b.kind]) || (a.order - b.order); });
  }

  /** 종류별 무리: units(정면·입체·미분류 묶음) · plan · small(서랍·부품) · photo(사진·그림 아님) · guess. */
  function groups(items) {
    var list = (items || []).filter(function (it) { return it && it.nw > 0 && it.nh > 0; }).map(function (it, i) {
      return { id: it.id, nw: it.nw, nh: it.nh, label: String(it.label || '미분류'), seq: i,
        order: isFinite(it.order) ? it.order : i, tx: it.tx > 0 ? it.tx : 0 };
    }).sort(function (a, b) { return (a.order - b.order) || (a.seq - b.seq); });
    var known = list.filter(function (it) { return FRONT[it.label] || ISO[it.label]; });
    var frontH = known.filter(function (k) { return FRONT[k.label]; }).map(function (k) { return k.nh; });
    var g = { main: [], plan: [], small: [], photo: [], all: list, guess: {} };
    list.forEach(function (it) {
      var twin = known.filter(function (k) { return k !== it && sameSize(k, it); })[0];
      var small = it.label === '서랍 단면' || it.label === '부품 상세';
      if (FRONT[it.label] || ISO[it.label] || it.label === '미분류' || (small && twin)) {
        it.kind = FRONT[it.label] ? 'front' : (ISO[it.label] ? 'iso' : (twin ? (FRONT[twin.label] ? 'front' : 'iso') : 'other'));
        if (it.kind === 'other' && frontH.some(function (h) { return Math.abs(it.nh - h) <= 0.03 * h; })) { it.kind = 'front'; }
        it.promoted = small;
        g.main.push(it);
      } else if (it.label === '평면·상판') { it.kind = 'plan'; g.plan.push(it); }
      else if (small) { it.kind = 'small'; g.small.push(it); }
      else { it.kind = 'photo'; g.photo.push(it); }
    });
    g.photo.sort(function (a, b) { return ((a.label === '그림 아님') - (b.label === '그림 아님')) || (a.order - b.order) || (a.seq - b.seq); });
    g.units = pairUp(g.main, g.guess);
    return g;
  }

  /** 모두 줄에 둘 때도 종류를 모르는 그림 중 키가 유난히 다른 것(예: 이름이 늦은 휴대폰 사진)은 남은 칸으로 —
      같은 배율로 줄에 넣으면 그 한 장 때문에 모듈 그림이 다 작아진다. */
  function coreRows(units) {
    var hs = units.map(unitH).sort(function (a, b) { return a - b; });
    var med = hs.length ? hs[(hs.length - 1) >> 1] : 0, rows = [], out = [];
    units.forEach(function (u) {
      var h = unitH(u);
      (u.kind !== 'other' || (h >= 0.6 * med && h <= 1.6 * med) ? rows : out).push(u);
    });
    return { rows: rows, extra: out };
  }

  function context(P, g, area, obstacles, reserve, minText, probe) {
    var blocks = (obstacles || []).slice();
    if (reserve) { blocks.push(reserve); }
    var front = g.units.filter(function (u) { return u.kind === 'front'; });
    var rest = g.units.filter(function (u) { return u.kind !== 'front'; });
    var variants = [coreRows(g.units)];
    if (front.length && rest.length) { variants.unshift({ rows: front, extra: rest }); }   // 입체·미분류 묶음은 남은 칸에
    var starts = [area.y0];
    if (reserve && reserve.y + reserve.h + GAP < area.y1 && reserve.y + reserve.h + GAP > area.y0) { starts.push(reserve.y + reserve.h + GAP); }
    var usable = (area.x1 - area.x0) * (area.y1 - area.y0), tallest = 1, good = Math.max(GOOD_TEXT, minText + 1.5);
    if (reserve) {   // 채운 넓이는 자재표 자리를 뺀 넓이에 견준다
      usable -= Math.max(0, Math.min(area.x1, reserve.x + reserve.w) - Math.max(area.x0, reserve.x)) *
        Math.max(0, Math.min(area.y1, reserve.y + reserve.h) - Math.max(area.y0, reserve.y));
    }
    g.all.forEach(function (it) { tallest = Math.max(tallest, it.nh); });
    return { P: P, g: g, area: area, blocks: blocks, variants: variants, starts: starts, free0: P.freeRects(area, blocks, 0),
      minText: minText, usable: Math.max(1, usable), tallest: tallest, hasRows: g.units.length > 0, photoMin: PHOTO_MIN,
      good: good, floors: probe ? [0] : [good, 0],
      tail: g.plan.map(one).concat(g.small.map(one), g.photo.map(one)),
      hasText: g.all.some(function (it) { return it.tx > 0 && it.kind !== 'photo'; }) };
  }

  function textPx(it, scale) { return (it.tx > 0 && it.kind !== 'photo') ? it.tx * scale : Infinity; }
  /** 묶음을 이 높이 밑으로는 줄이지 않는다 — 현장 사진은 photoMin, 글자가 있는 그림은 치수 글자가 px 가 되는 높이(확대 상한 안). */
  function floorH(ctx, u, px) {
    var hN = unitH(u), need = Math.max.apply(null, u.members.map(function (m) {
      return m.label === '사진' ? ctx.photoMin : (px > 0 && m.tx > 0 && m.kind !== 'photo' ? px * hN / m.tx : 0); }));
    return Math.min(Math.ceil(need), Math.round(hN * MAX_UP));
  }
  /** 묶음 하나를 배율 sc 로 놓을 크기 — 짝은 옆으로 붙인다. */
  function block(u, sc) {
    var ws = u.members.map(function (m) { return Math.max(1, Math.round(m.nw * sc)); });
    var hs = u.members.map(function (m) { return Math.max(1, Math.round(m.nh * sc)); });
    return { ws: ws, hs: hs, w: ws.reduce(function (a, b) { return a + b; }, 0) + GAP * (ws.length - 1), h: Math.max.apply(null, hs) };
  }

  /** 남은 빈 칸에 묶음을 차례로 넣는다. fixed 묶음은 줄 배율 s 그대로, 나머지는 줄 높이의 비율(× cap)로 큰 것부터 —
      strict 면 floorH(글자 floor px · 사진 하한) 밑으로는 줄이지 않는다. */
  function fill(ctx, free, list, mainH, s, strict, cap, floor) {
    var areaW = ctx.area.x1 - ctx.area.x0, placed = [];
    for (var i = 0; i < list.length; i++) {
      var u = list[i].unit, grp = list[i].fixed ? 'unit' : (RATIOS[u.kind] ? u.kind : 'iso'), hN = unitH(u);
      var top = u.kind === 'other' ? Math.max(Math.round(hN * s), floorH(ctx, u, ctx.minText)) : Infinity;   // 모르면 줄 배율만큼(글자는 지킴)
      var lo = strict && !list[i].fixed ? Math.min(floorH(ctx, u, floor), top) : 0;
      var ratios = list[i].fixed ? [0] : (strict ? RATIOS[grp] : RATIOS[grp].concat(RATIOS.tight));
      var rect = null, bl = null, last = -1;
      for (var r = 0; r < ratios.length && !rect; r++) {
        var sc = s;
        if (!list[i].fixed) {
          var hh = Math.min(Math.round(mainH * ratios[r] * cap), Math.round(hN * MAX_UP), top);
          sc = Math.max(hh, lo) / hN;
        }
        bl = block(u, sc);
        if (bl.w > areaW) { sc *= (areaW - GAP * (bl.ws.length - 1)) / (bl.w - GAP * (bl.ws.length - 1)); bl = block(u, sc); }
        if (bl.h === last) { continue; }
        last = bl.h;
        if (strict && u.members.some(function (m) { return textPx(m, sc) < ctx.minText; })) { continue; }
        rect = ctx.P.pick(free, bl.w, bl.h, MODE[grp]);
      }
      if (!rect) { return null; }
      for (var k = 0, x = rect.x; k < u.members.length; x += bl.ws[k] + GAP, k++) {
        placed.push({ id: u.members[k].id, x: x, y: rect.y + bl.h - bl.hs[k], w: bl.ws[k], h: bl.hs[k] });
      }
      free = ctx.P.cut(free, pad(rect, GAP));
    }
    return { placed: placed, free: free };
  }

  function rowArea(area, W) {
    return W < 1 ? { x0: area.x0, y0: area.y0, x1: Math.round(area.x0 + (area.x1 - area.x0) * W), y1: area.y1 } : area;
  }

  /** 배율 s · 시작 y · 줄 폭 W 로 줄을 놓고 남은 칸을 채운다. strict 면 글자 하한을 지키는 크기만 쓴다. 실패하면 null. */
  function evaluate(ctx, cfg, s, y0, W, strict) {
    var P = ctx.P, area = ctx.area;
    var sh = cfg.rows.length ? P.shelves(cfg.rows, s, rowArea(area, W), ctx.blocks, y0, GAP, true) : { placed: [], bands: [], rest: [] };
    if (!sh) { return null; }
    var mainH = 0, free = ctx.free0, got = null;
    sh.placed.forEach(function (p) { mainH = Math.max(mainH, p.h); });
    mainH = mainH || Math.max(1, Math.round(s * ctx.tallest));
    sh.bands.forEach(function (b) { free = P.cut(free, pad(b, GAP)); });
    var list = sh.rest.map(function (u) { return { unit: u, fixed: true }; })
      .concat(cfg.extra.concat(ctx.tail).map(function (u) { return { unit: u }; }));
    for (var f = 0; f < (strict ? ctx.floors.length : 1) && !got; f++) {   // 글자 9.5px 로 먼저, 안 되면 하한까지
      for (var k = 0; k < SHRINK.length && !got; k++) { got = fill(ctx, free, list, mainH, s, strict, SHRINK[k], ctx.floors[f]); }
    }
    if (!got || (strict && !ctx.hasText && ctx.hasRows && mainH < FALLBACK_H)) { return null; }
    var placed = sh.placed.concat(got.placed), byId = {}, cover = 0, planR = 1, minText = Infinity, hole = 0;
    ctx.g.all.forEach(function (it) { byId[it.id] = it; });
    placed.forEach(function (p) {
      var it = byId[p.id];
      cover += p.w * p.h;
      minText = Math.min(minText, textPx(it, p.h / it.nh));
      if (it.kind === 'plan') { planR = Math.min(planR, p.h / mainH); }
    });
    got.free.forEach(function (f) { hole = Math.max(hole, f.w * f.h); });
    // 글자를 지킬 때: 채운 넓이 + 큰 그림 줄 높이 − 가장 큰 빈 칸 + 평면 크기 + 가장 작은 글자(9.5px 까지). 못 지킬 때: 가장 작은 글자
    var good = minText === Infinity ? 1 : Math.max(0, Math.min(1, (minText - ctx.minText) / (ctx.good - ctx.minText)));
    var score = strict ? (cover - 0.5 * hole) / ctx.usable + 0.6 * mainH / (area.y1 - area.y0) + 0.1 * Math.min(1, planR / 0.8) +
      0.2 * good : (minText === Infinity ? mainH / 20 : minText) + 0.01 * cover / ctx.usable;
    return { placed: placed, scale: s, mainH: mainH, minText: minText === Infinity ? null : Math.round(minText * 10) / 10, score: score };
  }

  /** 재 볼 배율(큰 것부터): 줄에 다 들어가는 가장 큰 배율에서 0.93배씩 + 그보다 크게(뒤쪽 묶음은 빈 칸으로) 첫 묶음이 들어가는 배율부터. */
  function scales(ctx, cfg, y0, W, lo, strict) {
    var area = ctx.area, ra = rowArea(area, W), rows = flat(cfg.rows), out = [];
    var hi = Math.min(MAX_UP, (area.y1 - y0) / (rows.length ? unitH({ members: rows }) : ctx.tallest));
    cfg.rows.forEach(function (u) { hi = Math.min(hi, (ra.x1 - ra.x0) / block(u, 1).w); });
    if (!(hi > 0)) { return out; }
    var all = ctx.P.maxScale(cfg.rows, ra, ctx.blocks, y0, GAP, hi);
    for (var j = 0; all > 0 && j < (strict ? STEPS : STEPS + 4); j++) { out.push(all * Math.pow(0.93, j)); }
    for (var s = hi; s > all * 1.001 && s >= lo && out.length < 2 * MAX_TRY; s *= 0.93) { out.push(s); }
    out.sort(function (a, b) { return b - a; });
    return out.filter(function (v, i) { return v >= lo - 1e-9 && (!i || v < out[i - 1] * 0.995); }).slice(0, MAX_TRY);
  }

  function search(ctx, strict, probe) {
    var best = null;
    ctx.variants.forEach(function (cfg) {
      var lo = 0;
      flat(cfg.rows).forEach(function (m) { if (strict && m.tx > 0) { lo = Math.max(lo, ctx.minText / m.tx); } });
      ctx.starts.forEach(function (y0) {
        WIDTHS.forEach(function (W) {
          if (W < 1 && cfg.rows.length < 2) { return; }   // 묶음 하나면 줄 폭을 좁혀도 같다
          scales(ctx, cfg, y0, W, lo, strict).forEach(function (s) {
            if (probe && best) { return; }
            var c = evaluate(ctx, cfg, s, y0, W, strict);
            if (c && (!best || c.score > best.score + 1e-9)) { best = c; }
          });
        });
      });
    });
    return best;
  }

  /** 아무 후보도 안 되면: 가장 큰 빈 칸에 바둑판으로(장애물·자재표 자리는 그대로 피함). */
  function grid(ctx) {
    var f = null;
    ctx.free0.forEach(function (r) { if (!f || r.w * r.h > f.w * f.h) { f = r; } });
    var all = flat(ctx.g.units).concat(ctx.g.plan, ctx.g.small, ctx.g.photo), n = all.length;
    if (!f || !n) { return null; }
    var cols = Math.max(1, Math.ceil(Math.sqrt(n * f.w / f.h))), rowsN = Math.ceil(n / cols);
    var cw = Math.floor((f.w - GAP * (cols - 1)) / cols), ch = Math.floor((f.h - GAP * (rowsN - 1)) / rowsN);
    if (cw < 2 || ch < 2) { return null; }
    var minText = Infinity, placed = all.map(function (it, i) {
      var sc = Math.min(cw / it.nw, ch / it.nh, MAX_UP);
      minText = Math.min(minText, textPx(it, sc));
      return { id: it.id, x: f.x + (i % cols) * (cw + GAP), y: f.y + Math.floor(i / cols) * (ch + GAP),
        w: Math.max(1, Math.floor(it.nw * sc)), h: Math.max(1, Math.floor(it.nh * sc)) };
    });
    return { placed: placed, scale: 0, mainH: ch, minText: minText === Infinity ? null : Math.round(minText * 10) / 10 };
  }

  function arrange(items, area, obstacles, opts) {
    var P = window.FomsPartPack, o = opts || {};
    var minText = o.minText > 0 ? o.minText : MIN_TEXT;
    var none = { placed: [], scale: 0, mainH: 0, minText: null, crowded: false, guess: {}, why: '', photo: null };
    if (!P || !area || !(area.x1 - area.x0 > 40) || !(area.y1 - area.y0 > 40)) { return none; }
    var g = groups(items);
    if (!g.all.length) { return none; }
    var ctx = context(P, g, area, obstacles, o.reserve || null, minText, !!o.probe);
    var best = search(ctx, true, !!o.probe), crowded = !best, why = '', photo = Infinity, kind = {};
    if (!best && o.probe) { return { placed: [], scale: 0, mainH: 0, minText: null, crowded: true, guess: g.guess }; }
    // 사진 하한만 빼면 글자는 지켜지나 — 그러면 그 배치(사진만 작게)를 '그래도 이 시트에' 로 쓴다
    if (!best) { ctx.photoMin = 0; best = search(ctx, true, false); why = best ? 'photo' : 'text'; }
    best = best || search(ctx, false, false) || grid(ctx);
    if (!best) { return none; }
    if (!ctx.hasText && ctx.hasRows && best.mainH < FALLBACK_H) { crowded = true; why = 'text'; }
    g.all.forEach(function (it) { kind[it.id] = it.label; });
    best.placed.forEach(function (p) { if (kind[p.id] === '사진') { photo = Math.min(photo, p.h); } });
    return { placed: best.placed, scale: Math.round(best.scale * 10000) / 10000, mainH: best.mainH, minText: best.minText,
      crowded: crowded, guess: g.guess, why: why, photo: photo === Infinity ? null : photo };
  }

  window.FomsPartLayout = { arrange: arrange, groups: groups, MIN_TEXT: MIN_TEXT, PHOTO_MIN: PHOTO_MIN };
})();
