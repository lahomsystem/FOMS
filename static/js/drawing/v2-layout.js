/**
 * 도면 마법사 V2 — 틀 두 가지(위 띠형 · 왼쪽 기둥형)를 모두 계산해 그림이 크게 나오는 쪽을 고른다(순수 계산).
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §3 · §4 (화면 시안 K2-WizardAuto)
 * - 위 띠형: 위 띠 = [사진][자재 + 특이][B 상세][평면] · 오른쪽 위 강조 문구, 아래 = 큰 그림 칸(정면 · 입체 짝 줄).
 * - 왼쪽 기둥형: 왼쪽 기둥 = [사진][상세][평면], 오른쪽 위 = [자재][특이][강조], 오른쪽 아래 = 큰 그림 칸.
 * - 큰 그림이 없으면 상세 · 평면이 큰 그림 자리를 쓴다. 미분류 그림은 맨 아래 낮은 '기타 그림' 줄(큰 그림과 배율을 나누지 않음).
 * - 띠 높이 · 기둥 폭을 여러 값으로 재 본다. 점수 = 가장 작은 그림 % + 큰 그림 %의 절반 − 치수 글자 하한 벌점.
 *   % = 지금 양식 대비(같은 그림을 V1 자동 배치로 놓았을 때 높이 — input.base), 없으면 원본 대비.
 * - 치수 글자가 8px 밑이거나 가장 작은 그림이 60% 밑이면 crowded(나누기를 권함). 기준(V1 자동 배치)은 빈 종이에 큰 그림을
 *   가득 키운 크기라 80% 로 두면 그림 넷뿐인 시트에도 나누기를 권했다(로컬 실화면 2026-10-26).
 * - 장애물(input.obstacles = 그 자리에 남는 고정 그림 · 잠긴 글자)이 있으면 종이 칸 그대로와 장애물을 뺀 빈 사각형 중 큰 셋에서
 *   틀을 재고, 장애물에 닿는 틀은 버린다. 큰 그림 칸은 그 안의 장애물을 비켜 간다(v2-pack room). 예전엔 고정 그림 자리를 비우지 않아
 *   다시 놓은 그림이 그 위에 겹쳤고(스테이징 주문 4385, 2026-10-27), 고친 뒤엔 틀 전체를 빈 사각형 하나로 옮겨 그림이 작아졌다.
 * - 칸은 머리 최소 폭(HEAD_MIN_W — v2-paper.js 와 같음)만큼 자리를 잡는다. 좁은 칸 머리가 옆 칸 머리 위로 뻗어 겹쳤다.
 * - 주 그림 크게(opts.hero, 기본 켬 — v2-hero.js): 추천까지 정한 뒤 큰 그림 칸(res.big)만 주 그림 + 나머지로 다시 놓는다.
 *
 * window.FomsV2Layout = { AREA, compute(input, opts) → { band, column, best, rec }, MIN_TEXT, CROWD_PCT, HEAD_MIN_W }
 *   input: { area?, base: {id:{w,h}}, photo, detail, plan, unsorted: [item], units: [{slot, members:[item]}],
 *            bom: [{id,w,h}], notes: [{id,w,h}], stamp: {id,w,h}|null, obstacles?: [{x,y,w,h}] }   item = { id, nw, nh, tx }
 *   opts : { sameScale (기본 true), photoFirst (기본 true), hero (기본 true), prefer: 'band'|'column'|'' , minText: 8 }
 *   best = 붙일 틀(사람이 고른 틀이 놓이면 그것) · rec = 점수가 높은 틀(추천 표시 — 고른 틀과 다를 수 있다)
 *   틀 결과: { template, moves: [{id,x,y,w,h}], slots: [{key,x,y,w,h}], pct: {id: 비율}, minPct, minId, mainPct,
 *             minText, score, crowded, pctBase: 'v1'|'natural', big: {x,y,w,h}, hero?: [id](mainPct = 주 그림 %) } 또는 null(못 놓음)
 */
(function () {
  'use strict';
  if (window.FomsV2Layout) { return; }

  var AREA = { x0: 53, y0: 53, x1: 1427, y1: 848 };
  var COLGAP = 18, NOTE_PAD_X = 7, NOTE_PAD_Y = 3, STAMP_PAD = 10, NOTE_MIN_W = 300;
  var UNSORTED_H = 170, UNSORTED_W = 200, HEAD_MIN_W = 132;
  var MIN_TEXT = 8, CROWD_PCT = 0.6;   // 나누기 권함: 치수 글자 8px 밑(V1 과 같은 기준) 또는 지금 양식 대비 60% 밑

  function pk() { return window.FomsV2Pack; }
  function sum(a) { return a.reduce(function (s, v) { return s + v; }, 0); }

  function bomBlock(bom) {
    var x = 0, cols = bom.map(function (b, i) { var c = { id: b.id, x: x + (i ? COLGAP : 0), w: b.w, h: b.h }; x = c.x + b.w; return c; });
    return { cols: cols, w: x, h: bom.length ? Math.max.apply(null, bom.map(function (b) { return b.h; })) : 0 };
  }
  function noteFlow(notes, W) {
    return pk().flow(notes.map(function (n) { return { id: n.id, w: n.w + 2 * NOTE_PAD_X, h: n.h + 2 * NOTE_PAD_Y }; }), W, 8);
  }
  function stampBox(s) { return s ? { id: s.id, w: s.w + 2 * STAMP_PAD, h: s.h + 2 * STAMP_PAD } : null; }

  function newRes(template) { return { template: template, moves: [], slots: [] }; }
  function addPics(res, placed, ox, oy) {
    placed.forEach(function (p) { res.moves.push({ id: p.id, x: Math.round(ox + p.x), y: Math.round(oy + p.y), w: p.w, h: p.h }); });
  }
  function addSlot(res, key, x, y, w, h) { res.slots.push({ key: key, x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) }); }

  /** 자재표 칸(머리 + 열)과 특이 사항(머리 + 딱지 흐름)을 (x, y)에 놓는다. notesAt = 특이 칸 왼쪽 위(없으면 자재 아래). */
  function putBom(res, inp, x, y) {
    var HEAD = pk().HEAD, b = bomBlock(inp.bom);
    if (!inp.bom.length) { return { w: 0, h: 0 }; }
    addSlot(res, 'bom', x, y, b.w, HEAD + b.h);
    b.cols.forEach(function (c) { res.moves.push({ id: c.id, x: Math.round(x + c.x), y: Math.round(y + HEAD), w: c.w, h: c.h }); });
    return { w: b.w, h: HEAD + b.h };
  }
  function putNotes(res, inp, x, y, W) {
    var HEAD = pk().HEAD;
    if (!inp.notes.length) { return { w: 0, h: 0 }; }
    var f = noteFlow(inp.notes, W);
    addSlot(res, 'notes', x, y, W, HEAD + f.h);
    f.placed.forEach(function (p) {
      res.moves.push({ id: p.id, x: Math.round(x + p.x + NOTE_PAD_X), y: Math.round(y + HEAD + p.y + NOTE_PAD_Y), w: p.w - 2 * NOTE_PAD_X, h: p.h - 2 * NOTE_PAD_Y });
    });
    return { w: W, h: HEAD + f.h };
  }
  function putStamp(res, st, x, y) {
    if (!st) { return; }
    addSlot(res, 'stamp', x, y, st.w, st.h);
    res.moves.push({ id: st.id, x: Math.round(x + STAMP_PAD), y: Math.round(y + STAMP_PAD), w: st.w - 2 * STAMP_PAD, h: st.h - 2 * STAMP_PAD });
  }

  /** 큰 그림 칸 묶음 — 큰 그림이 있으면 [정면(main) · 입체(iso)], 없으면 [상세 · 평면]. 미분류는 늘 맨 뒤. */
  function bigGroups(inp) {
    var g = [], hasUnits = inp.units.length > 0;
    function units(list) { return list.map(function (it) { return { members: [it] }; }); }
    if (hasUnits) {
      ['main', 'iso'].forEach(function (k) {
        var u = inp.units.filter(function (x) { return x.slot === k; });
        if (u.length) { g.push({ key: k, units: u }); }
      });
    } else {
      if (inp.detail.length) { g.push({ key: 'detail', units: units(inp.detail) }); }
      if (inp.plan.length) { g.push({ key: 'plan', units: units(inp.plan) }); }
    }
    return { groups: g, smallKeys: hasUnits ? ['detail', 'plan'] : [] };
  }

  /** 큰 그림 칸 + 미분류. 미분류 그림은 큰 그림과 배율을 나누지 않고 따로 둔다 — 같이 두면 사람이 종류를 고르기 전까지
      큰 그림이 반으로 작아졌다(로컬 실화면 2026-10-26). 맨 아래 낮은 줄(높이 UNSORTED_H 까지)과 오른쪽 좁은 기둥
      (폭 UNSORTED_W 까지)을 둘 다 재 보고 큰 그림이 크게 나오는 쪽. */
  function putBig(res, inp, big, x, y, W, H, same) {
    var P = pk(), none = { placed: [], slots: [], t: Infinity };
    function lay(w, h) { return big.groups.length ? P.shelves(big.groups, w, h, same) : none; }
    function mark(w, h) { if (big.groups.length) { res.big = { x: x, y: y, w: w, h: h }; } }   // 큰 그림 칸 자리 — refine(bento)
    if (!inp.unsorted.length) {
      var only = lay(W, H);
      if (!only) { return false; }
      mark(W, H);
      addPics(res, only.placed, x, y);
      only.slots.forEach(function (s) { addSlot(res, s.key, x + s.x, y + s.y, s.w, s.h); });
      return true;
    }
    var below = P.row(inp.unsorted, W, UNSORTED_H - P.HEAD, same), side = P.stack(inp.unsorted, UNSORTED_W, H - P.HEAD, same);
    var sideW = side ? Math.max(side.w, HEAD_MIN_W) : 0;   // 좁은 기둥도 머리 폭만큼 — 머리가 칸 밖(고정 그림 · 종이 끝)으로 뻗지 않게
    var a = below ? lay(W, H - (P.HEAD + below.h + P.GAP)) : null, b = side ? lay(W - sideW - P.GAP, H) : null;
    var useSide = !!b && (!a || b.t > a.t * 1.001), sh = useSide ? b : a;
    if (!sh) { return false; }
    if (useSide) { mark(W - sideW - P.GAP, H); } else { mark(W, H - (P.HEAD + below.h + P.GAP)); }
    addPics(res, sh.placed, x, y);
    sh.slots.forEach(function (s) { addSlot(res, s.key, x + s.x, y + s.y, s.w, s.h); });
    if (useSide) {
      var sx = x + W - sideW;
      addSlot(res, 'unsorted', sx, y, side.w, P.HEAD + side.h);
      addPics(res, side.placed, sx, y + P.HEAD);
    } else {
      var top = y + H - (P.HEAD + below.h);
      addSlot(res, 'unsorted', x, top, below.w, P.HEAD + below.h);
      addPics(res, below.placed, x, top + P.HEAD);
    }
    return true;
  }

  /** 위 띠형 — 띠 높이 Hb. 띠 칸(자재 · 상세 · 평면 · 사진)은 머리 최소 폭만큼은 자리를 잡는다. */
  function band(inp, o, Hb) {
    var P = pk(), A = inp.area, W = A.x1 - A.x0, HEAD = P.HEAD, GAP = P.GAP;
    var res = newRes('band'), same = o.sameScale !== false, big = bigGroups(inp);
    var hasBom = inp.bom.length > 0, hasNotes = inp.notes.length > 0;
    var colW = hasBom ? Math.max(bomBlock(inp.bom).w, HEAD_MIN_W, hasNotes ? NOTE_MIN_W : 0) : (hasNotes ? NOTE_MIN_W + 40 : 0);
    var nH = hasNotes ? HEAD + noteFlow(inp.notes, colW).h : 0;
    var colH = (hasBom ? HEAD + bomBlock(inp.bom).h : 0) + (hasNotes ? (hasBom ? GAP : 0) + nH : 0);
    var st = stampBox(inp.stamp);
    var smalls = big.smallKeys.concat(['photo']).filter(function (k) { return inp[k].length; });
    var anyBand = colW > 0 || smalls.length > 0;
    if (!anyBand) { Hb = 0; }
    if (anyBand && (colH > Hb || (st && st.h > Hb) || Hb - HEAD < 40)) { return null; }
    var cH = Hb - HEAD;
    var avail = W - (colW ? colW + GAP : 0) - (st ? st.w + GAP : 0) - GAP * Math.max(0, smalls.length - 1);
    function widths(k) {
      return smalls.map(function (key) { var r = P.row(inp[key], Infinity, cH * k, same); return r ? Math.max(r.w, HEAD_MIN_W) : Infinity; });
    }
    var k = 1;
    if (smalls.length && sum(widths(1)) > avail) {
      var lo = 0, hi = 1;
      for (var i = 0; i < 24; i++) { var mid = (lo + hi) / 2; if (sum(widths(mid)) <= avail) { lo = mid; } else { hi = mid; } }
      k = lo;
      if (!(k > 0.05)) { return null; }
    }
    var order = o.photoFirst === false ? ['col'].concat(big.smallKeys, ['photo']) : ['photo', 'col'].concat(big.smallKeys);
    var x = A.x0;
    order.forEach(function (key) {
      if (key === 'col') {
        if (!colW) { return; }
        var b = putBom(res, inp, x, A.y0);
        putNotes(res, inp, x, A.y0 + (b.h ? b.h + GAP : 0), colW);
        x += colW + GAP;
        return;
      }
      if (!inp[key].length) { return; }
      var r = P.row(inp[key], Infinity, cH * k, same);
      addSlot(res, key, x, A.y0, r.w, HEAD + r.h);
      addPics(res, r.placed, x, A.y0 + HEAD);
      x += Math.max(r.w, HEAD_MIN_W) + GAP;
    });
    if (st) { putStamp(res, st, A.x1 - st.w, A.y0); }
    var y = A.y0 + (anyBand ? Hb + GAP : 0), room = P.room(A.x0, y, W, A.y1 - y, inp.obstacles, big.groups, same);
    return putBig(res, inp, big, room.x, room.y, room.w, room.h, same) ? res : null;
  }

  /** 왼쪽 기둥형 — 기둥 폭 Wc. */
  function column(inp, o, Wc) {
    var P = pk(), A = inp.area, W = A.x1 - A.x0, H = A.y1 - A.y0, HEAD = P.HEAD, GAP = P.GAP;
    var res = newRes('column'), same = o.sameScale !== false, big = bigGroups(inp);
    var leftKeys = (o.photoFirst === false ? big.smallKeys.concat(['photo']) : ['photo'].concat(big.smallKeys))
      .filter(function (k) { return inp[k].length; });
    if (!leftKeys.length) { return null; }   // 기둥에 넣을 것이 없으면 위 띠형과 같다
    var rx = A.x0 + Wc + GAP, RW = A.x1 - rx;
    // 왼쪽 기둥: 사진은 기둥 폭 · 높이 40% 안, 나머지(상세 · 평면)는 남은 높이에 한 배율로
    var y = A.y0;
    var photoAt = leftKeys.indexOf('photo'), rest = leftKeys.filter(function (k) { return k !== 'photo'; });
    var ph = null;
    if (photoAt >= 0) {
      ph = P.stack(inp.photo, Wc, (rest.length ? 0.4 * H : H) - HEAD, same);
      if (!ph) { return null; }
    }
    var restH = H - (ph ? ph.h + HEAD + GAP : 0);
    var sh = rest.length ? P.shelves(rest.map(function (k) {
      return { key: k, units: inp[k].map(function (it) { return { members: [it] }; }) };
    }), Wc, restH, same) : { placed: [], slots: [], h: 0 };
    if (!sh) { return null; }
    function putPhoto() {
      addSlot(res, 'photo', A.x0, y, ph.w, HEAD + ph.h);
      addPics(res, ph.placed, A.x0, y + HEAD);
      y += HEAD + ph.h + GAP;
    }
    if (ph && photoAt === 0) { putPhoto(); }
    addPics(res, sh.placed, A.x0, y);
    sh.slots.forEach(function (s) { addSlot(res, s.key, A.x0 + s.x, y + s.y, s.w, s.h); });
    y += sh.h + (sh.h ? GAP : 0);
    if (ph && photoAt > 0) { putPhoto(); }
    // 오른쪽 위: 자재 · 특이 · 강조(특이는 자재 머리 최소 폭 뒤에서 — 머리끼리 겹치지 않게)
    var st = stampBox(inp.stamp), b = putBom(res, inp, rx, A.y0), bw = b.w ? Math.max(b.w, HEAD_MIN_W) + GAP : 0;
    var notesW = RW - bw - (st ? st.w + GAP : 0), nh;
    if (inp.notes.length && notesW >= NOTE_MIN_W) {
      nh = putNotes(res, inp, rx + bw, A.y0, notesW).h;
    } else {
      nh = putNotes(res, inp, rx, A.y0 + (b.h ? b.h + GAP : 0), Math.max(b.w, NOTE_MIN_W)).h;
      nh = nh ? nh + (b.h ? b.h + GAP : 0) : 0;
    }
    if (st) { putStamp(res, st, A.x1 - st.w, A.y0); }
    var topH = Math.max(b.h, nh, st ? st.h : 0);
    var by = A.y0 + (topH ? topH + GAP : 0), room = P.room(rx, by, RW, A.y1 - by, inp.obstacles, big.groups, same);
    return putBig(res, inp, big, room.x, room.y, room.w, room.h, same) ? res : null;
  }

  function score(res, inp, o) {
    var base = inp.base || {}, byId = inp.byId, hasBase = Object.keys(base).length > 0;
    var minPct = Infinity, minId = null, mainPct = Infinity, minText = Infinity, pct = {};
    res.moves.forEach(function (m) {
      var it = byId[m.id];
      if (!it || !(it.nh > 0)) { return; }
      var b = base[m.id], p = hasBase ? (b && b.h > 0 ? m.h / b.h : null) : m.h / it.nh;
      if (p != null) { pct[m.id] = p; }
      if (it.slot === 'photo' || it.slot === 'unsorted') { return; }   // 사진 · 종류를 고르기 전 그림은 '가장 작은 그림'에서 뺀다
      if (p != null && p < minPct) { minPct = p; minId = m.id; }
      if (p != null && (it.slot === 'main' || it.slot === 'iso') && (!res.hero || res.hero.indexOf(m.id) >= 0)) { mainPct = Math.min(mainPct, p); }
      if (it.tx > 0) { minText = Math.min(minText, it.tx * m.h / it.nh); }
    });
    var lim = o.minText > 0 ? o.minText : MIN_TEXT, mp = minPct === Infinity ? 1 : minPct;
    res.pct = pct;
    res.pctBase = hasBase ? 'v1' : 'natural';
    res.minPct = minPct === Infinity ? null : minPct;
    res.minId = minId;
    res.mainPct = mainPct === Infinity ? null : mainPct;
    res.minText = minText === Infinity ? null : Math.round(minText * 10) / 10;
    res.score = mp + 0.5 * (mainPct === Infinity ? mp : mainPct) - (minText < lim ? 2 + (lim - minText) : 0);
    res.crowded = (hasBase && minPct !== Infinity && minPct < CROWD_PCT) || minText < lim;
    return res;
  }

  function best(list, inp, o) {
    var top = null;
    list.forEach(function (r) {
      if (!r) { return; }
      score(r, inp, o);
      if (!top || r.score > top.score + 1e-9) { top = r; }
    });
    return top;
  }

  /** 틀을 잴 칸(꼴 { x0, y0, x1, y1 }) — 종이 칸 그대로 + 장애물이 있으면 그것을 뺀 빈 사각형 중 넓은 셋. 종이 칸에서 잰 틀은
      장애물에 닿지 않을 때만 남는다(keep) — 큰 그림 칸이 고정 그림을 비켜 가면(v2-pack room) 틀을 통째로 옮기지 않아도 된다. */
  function areasOf(full, obs) {
    if (!obs.length || !window.FomsPartPack) { return [full]; }
    return [full].concat(window.FomsPartPack.freeRects(full, obs, pk().GAP).map(function (f) { return { x0: f.x, y0: f.y, x1: f.x + f.w, y1: f.y + f.h }; })
      .filter(function (a) { return a.x0 !== full.x0 || a.y0 !== full.y0 || a.x1 !== full.x1 || a.y1 !== full.y1; })
      .sort(function (a, b) { return (b.x1 - b.x0) * (b.y1 - b.y0) - (a.x1 - a.x0) * (a.y1 - a.y0); }).slice(0, 3));
  }
  function hitsAny(r, obs) {
    return obs.some(function (b) { return r.moves.some(function (m) { return m.x < b.x + b.w && b.x < m.x + m.w && m.y < b.y + b.h && b.y < m.y + m.h; }); });
  }

  function compute(input, opts) {
    var o = opts || {}, inp = {};
    ['photo', 'detail', 'plan', 'unsorted', 'units', 'bom', 'notes'].forEach(function (k) { inp[k] = (input && input[k]) || []; });
    inp.stamp = (input && input.stamp) || null;
    inp.base = (input && input.base) || {};
    inp.area = (input && input.area) || AREA;
    inp.byId = {};
    function mark(list, slot) { list.forEach(function (it) { inp.byId[it.id] = { nw: it.nw, nh: it.nh, tx: it.tx || 0, slot: slot }; }); }
    ['photo', 'detail', 'plan', 'unsorted'].forEach(function (k) { mark(inp[k], k); });
    inp.units.forEach(function (u) { mark(u.members, u.slot); });
    var obs = (input && input.obstacles) || [], full = inp.area, bands = [], cols = [], v;
    inp.obstacles = obs;
    function keep(list, r) { list.push(r && obs.length && hitsAny(r, obs) ? null : r); }   // 장애물에 닿는 틀은 버린다
    areasOf(full, obs).forEach(function (ar) {
      var H = ar.y1 - ar.y0, W = ar.x1 - ar.x0;
      inp.area = ar;
      for (v = 64; v <= 0.55 * H; v += 8) { keep(bands, band(inp, o, v)); }
      keep(bands, band(inp, o, 0));
      for (v = 160; v <= 0.45 * W; v += 12) { keep(cols, column(inp, o, v)); }
    });
    inp.area = full;
    var out = { band: best(bands, inp, o), column: best(cols, inp, o) };
    out.rec = out.band && out.column ? (out.column.score > out.band.score + 0.005 ? 'column' : 'band') : (out.band ? 'band' : (out.column ? 'column' : ''));
    var H = window.FomsV2Hero, kit = { groups: bigGroups(inp).groups, score: function (r) { return score(r, inp, o); } };
    if (H) { out.band = H.refine(out.band, inp, o, kit); out.column = H.refine(out.column, inp, o, kit); }   // 추천을 정한 뒤 — 나머지가 줄어 점수가 깎인다
    var pref = o.prefer === 'column' || o.prefer === 'band' ? o.prefer : '';
    out.best = pref && out[pref] ? pref : out.rec;
    return out;
  }

  window.FomsV2Layout = { AREA: AREA, compute: compute, MIN_TEXT: MIN_TEXT, CROWD_PCT: CROWD_PCT, HEAD_MIN_W: HEAD_MIN_W,
    NOTE_PAD_X: NOTE_PAD_X, NOTE_PAD_Y: NOTE_PAD_Y, STAMP_PAD: STAMP_PAD, COLGAP: COLGAP };
})();
