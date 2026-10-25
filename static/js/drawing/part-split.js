/**
 * 도면 마법사 — 그림이 많아 치수 글자를 지킬 수 없을 때 시트 나누기 계획(순수 계산, 화면을 건드리지 않는다).
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.2 (다 안 들어가면 더 줄이지 않고 나누기)
 * - 놓는 순서 그대로 묶음(짝은 함께) 단위로 나눈다: 정면 → 입체 → 미분류 → 평면 → 서랍·부품 → 사진.
 * - 시트마다 글자를 지키며 들어가는 가장 긴 앞부분을 담고, 그 뒤 묶음 중 더 들어가는 것도 담는다(정면 모듈은 순서대로만).
 *   '지킨다' = part-layout.js 의 엄격한 배치(치수 글자 8px · 현장 사진 높이 120px) — 사진이 우표만 해질 시트면 사진도 옮긴다.
 * - 첫 시트는 지금 시트 칸(자재표 자리 그대로), 다음 시트부터는 새 시트 칸(자리표만 있는 빈 시트).
 * - 시트가 모자라면(maxSheets) 남은 그림은 마지막 시트에 모두 넣고 ok=false. 한 묶음도 글자를 못 지키면 그 묶음만 따로.
 *
 * window.FomsPartSplit = { plan(items, first, next, opts) → { sheets: [[id…]…], ok, counts: [{front, iso, other, plan, small, photo, n}] } }
 *   items : FomsPartLayout.arrange 와 같은 그림 목록   first·next : { area, obstacles, reserve }
 *   opts  : { minText, maxSheets(지금 시트 포함, 기본 10) }
 * part-pack.js · part-layout.js 를 먼저 불러야 한다. 같은 입력이면 늘 같은 답.
 */
(function () {
  'use strict';
  if (window.FomsPartSplit) { return; }

  var KINDS = ['front', 'iso', 'other', 'plan', 'small', 'photo'];

  function fits(list, geo, minText) {
    if (!list.length) { return true; }
    var res = window.FomsPartLayout.arrange(list, geo.area, geo.obstacles, { reserve: geo.reserve, minText: minText, probe: true });
    return res.placed.length > 0 && !res.crowded;
  }

  /** 놓는 순서대로 묶음 목록 [{ kind, items }] — 짝은 한 묶음. */
  function pieces(items) {
    var g = window.FomsPartLayout.groups(items), byId = {};
    (items || []).forEach(function (it) { if (it) { byId[it.id] = it; } });
    var pick = function (m) { return byId[m.id]; };
    var out = g.units.map(function (u) { return { kind: u.kind, items: u.members.map(pick) }; });
    ['plan', 'small', 'photo'].forEach(function (k) {
      g[k].forEach(function (m) { out.push({ kind: k, items: [pick(m)] }); });
    });
    return out;
  }

  function flat(list) { return list.reduce(function (a, p) { return a.concat(p.items); }, []); }

  function count(list) {
    var c = { n: 0 };
    KINDS.forEach(function (k) { c[k] = 0; });
    list.forEach(function (p) {
      c.n += p.items.length;
      c[p.kind] += p.kind === 'front' ? 1 : p.items.length;   // 정면은 묶음(모듈) 수, 나머지는 장수
    });
    return c;
  }

  function plan(items, first, next, opts) {
    var o = opts || {}, max = Math.max(1, Math.floor(o.maxSheets || 10)), minText = o.minText;
    var rest = pieces(items), sheets = [], ok = true;
    while (rest.length) {
      var geo = sheets.length ? next : first;
      if (sheets.length >= max - 1) {   // 마지막 시트 — 남은 것을 모두
        ok = ok && fits(flat(rest), geo, minText);
        sheets.push(rest);
        break;
      }
      var lo = 0, hi = rest.length;
      while (lo < hi) {
        var mid = (lo + hi + 1) >> 1;
        if (fits(flat(rest.slice(0, mid)), geo, minText)) { lo = mid; } else { hi = mid - 1; }
      }
      if (!lo) { lo = 1; ok = false; }   // 한 묶음도 글자를 못 지킨다 — 그 묶음만 따로(작게라도)
      var sheet = rest.slice(0, lo);
      rest = rest.slice(lo);
      for (var i = 0; i < rest.length && ok;) {   // 뒤쪽 묶음 중 더 들어가는 것(정면 모듈은 순서를 지키려고 빼고)
        var p = rest[i];
        if (p.kind !== 'front' && fits(flat(sheet.concat([p])), geo, minText)) {
          sheet.push(p);
          rest.splice(i, 1);
        } else { i++; }
      }
      sheets.push(sheet);
    }
    return {
      sheets: sheets.map(function (s) { return flat(s).map(function (it) { return it.id; }); }),
      ok: ok,
      counts: sheets.map(count)
    };
  }

  window.FomsPartSplit = { plan: plan };
})();
