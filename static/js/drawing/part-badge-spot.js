/**
 * 도면 마법사 — 그림 이름 딱지 자리 고르기(순수 계산) · 그림 잉크 지도.
 *
 * 사용성 재평가(2026-10-25 QA1·QA3): 그림 안 왼쪽 위에 얹던 딱지가 맨 위 치수('950'·'(100)'·'185')와 옆 자리표
 * '[SR]'를 가리고, 작은 그림에서는 딱지끼리 겹쳤다. 그래서 딱지마다 몇 자리를 견줘 가장 덜 가리는 곳에 둔다.
 * 마지막 실화면 확인(2026-10-25 V1): 그림 사이 틈(16px)이 딱지(20px)보다 좁아 '그림 틀 바로 위'가 윗그림 아래 치수('60')를
 * 덮었고, 1366 맞춤(74%)에서는 딱지가 그림보다 커 보여 '650'·'950 45'를 덮었다. 그래서
 * - 후보(왼쪽 위 점): 높이 다섯 줄(그림 틀 바로 위 바깥 · 틀에 걸침(딱지 30%·60% 가 그림 안) · 그림 안 위 · 그림 안 아래) ×
 *   가로 세 자리(왼쪽 끝 · 오른쪽 끝 · 가운데). 틀에 걸친 자리는 윗그림 대신 제 그림 위쪽 빈 곳을 쓴다.
 * - 값 = 덮는 넓이 × 무게(작을수록 좋다): 먼저 놓은 딱지 300 · 양식 칸(머리칸 글자·쪽번호 칸·아래 표)과 글자 객체 60 ·
 *   그림의 글자 같은 잉크 120(다른 그림 150) · 그 밖의 잉크(선) 5(다른 그림 10) · 그림 위(빈 곳이라도) 0.3(다른 그림 1) ·
 *   시트 밖 1000 · 뒤 후보일수록 조금씩(늘 같은 자리를 좋아하게). 사진 딱지가 제 사진 위에 앉는 값은 작다(사진엔 치수가 없다).
 *   잉크 지도가 없는 그림(아직 못 읽음·돌린 그림·다른 출처)은 잉크가 가득, 글자는 넓이의 1/4 로 본다.
 * - 긴 글('AI 72% · 정면·내부')이 그림 폭보다 길면 짧은 글(종류 이름만)로, 긴 글이 가릴 때 짧은 글이 덜 가리면 짧은 글로.
 * - 잉크 지도: 그림을 긴 변 256px 로 줄여 4×4 칸마다 가장 진한 점(진하기 1/3 이상은 가득) — 그림 원본에 붙여 한 번만 잰다.
 *   글자 지도(t)는 가로·세로로 길게 이어진 잉크(치수선·외곽선·빗금 판)를 뺀 나머지 — 숫자·글자 덩어리가 남는다.
 * - 딱지 크기(badgeScale): 줌 100% 이상은 화면에서 늘 12px, 100% 아래에서는 배율을 따라 줄되 80% 까지만(wizard.css 와 같은 식).
 *   (견본 시트 18장·줌 100/74/60% 모의에서 딱지가 덮은 글자 넓이가 63~79% 줄고 다른 그림 글자는 거의 0 — 딱지끼리 겹침 0)
 *
 * window.FomsPartBadgeSpot = { place(pics, items, blocks, bounds), inkFromPixels(rgba, w, h), inkGrid(src),
 *   inkCover(pic, x0, y0, x1, y1, key), badgeScale(zoom) }
 *   pics  : [{ id, r: {x, y, w, h}, ink }]  시트의 모든 그림(스테이지 좌표, 딱지가 없는 그림도 — 가리면 안 되는 내용)
 *   items : [{ id, fw, sw, bh, g, photo }]  딱지: 긴 글 폭 · 짧은 글 폭 · 높이 · 틈(모두 스테이지 좌표) · 사진인가, 놓는 순서대로
 *   blocks: [{ x, y, w, h }]  양식 칸 · 글자 객체        bounds: { w, h }  스테이지 크기
 *   → { id: { x, y, w, h, short } }
 *   (node 로 시험한다 — tests/domains/test_drawing_part_badge_spot.py)
 */
(function () {
  'use strict';
  if (window.FomsPartBadgeSpot) { return; }

  var SIDE = 256, CELL = 4;
  var RUN = 12, LINE_D = 0.25;   // 줄인 그림에서 진하기 0.25 이상인 잉크가 가로·세로로 12점 넘게 이어지면 선(글자 아님)
  var W_BADGE = 300, W_BLOCK = 60, W_OUT = 1000;
  var W_TEXT = 120, W_TEXT_OTHER = 150, W_INK = 5, W_INK_OTHER = 10, W_PIC = 0.3, W_PIC_OTHER = 1, W_INK_PHOTO = 0.5;
  var SHORT_COST = 0.4;   // 짧은 글은 긴 글 넓이의 0.4 만큼 손해로 친다(가리는 게 그보다 크면 짧은 글)
  var ORDER_COST = 0.02;  // 뒤 후보 한 칸마다 긴 글 넓이의 0.02
  var MIN_SCALE = 0.8;    // 줌을 줄여도 딱지는 화면에서 80% 까지만 준다(글자 9.6px)
  var UNKNOWN_T = 0.25;   // 잉크 지도가 없는 그림(아직 못 읽음·돌린 그림)의 글자 몫 — 예전처럼 양식 칸의 절반쯤으로 피한다

  function overlap(a0, a1, b0, b1) { return Math.max(0, Math.min(a1, b1) - Math.max(a0, b0)); }

  /** 그림 한 장 안으로 자른 칸 [x0,x1]×[y0,y1] 의 잉크 넓이(칸마다 진하기 × 겹친 넓이). key = 'v'(잉크, 기본) | 't'(글자 —
      글자 지도가 없는 잉크 지도는 잉크 전부를 글자로 본다). 잉크 지도가 없으면 잉크는 넓이 그대로, 글자는 넓이의 UNKNOWN_T. */
  function inkCover(pic, x0, y0, x1, y1, key) {
    var g = pic.ink, r = pic.r, vv = g && (g[key || 'v'] || g.v);
    if (!vv || !(r.w > 0) || !(r.h > 0)) {
      return Math.max(0, x1 - x0) * Math.max(0, y1 - y0) * (key === 't' ? UNKNOWN_T : 1);
    }
    var cw = r.w / g.w, ch = r.h / g.h, sum = 0;
    var i0 = Math.max(0, Math.floor((x0 - r.x) / cw)), i1 = Math.min(g.w - 1, Math.floor((x1 - r.x) / cw));
    var j0 = Math.max(0, Math.floor((y0 - r.y) / ch)), j1 = Math.min(g.h - 1, Math.floor((y1 - r.y) / ch));
    for (var j = j0; j <= j1; j++) {
      var oy = overlap(y0, y1, r.y + j * ch, r.y + (j + 1) * ch);
      for (var i = i0; oy > 0 && i <= i1; i++) {
        var v = vv[j * g.w + i];
        if (v > 0) { sum += v * oy * overlap(x0, x1, r.x + i * cw, r.x + (i + 1) * cw); }
      }
    }
    return sum;
  }

  /** 딱지 자리 b 의 값 — 그림(글자·선 잉크)·양식 칸·글자 객체·먼저 놓은 딱지·시트 밖을 덮는 만큼.
      제 그림(ctx.id)보다 다른 그림을 덮는 값이 무겁다(남의 치수를 가리고, 딱지가 그 그림 것으로 읽힌다). */
  function cost(b, ctx) {
    var x1 = b.x + b.w, y1 = b.y + b.h, c = 0;
    c += W_OUT * (b.w * b.h - overlap(b.x, x1, 0, ctx.bounds.w) * overlap(b.y, y1, 0, ctx.bounds.h));
    ctx.pics.forEach(function (p) {
      var r = p.r, ox0 = Math.max(b.x, r.x), oy0 = Math.max(b.y, r.y);
      var ox1 = Math.min(x1, r.x + r.w), oy1 = Math.min(y1, r.y + r.h);
      if (!(ox1 > ox0 && oy1 > oy0)) { return; }
      var own = p.id === ctx.id, photo = own && ctx.photo;
      var wt = own ? (photo ? 0 : W_TEXT) : W_TEXT_OTHER, wi = own ? (photo ? W_INK_PHOTO : W_INK) : W_INK_OTHER;
      c += (own ? W_PIC : W_PIC_OTHER) * (ox1 - ox0) * (oy1 - oy0) + wi * inkCover(p, ox0, oy0, ox1, oy1, 'v') +
        (wt ? wt * inkCover(p, ox0, oy0, ox1, oy1, 't') : 0);
    });
    ctx.blocks.forEach(function (k) { c += W_BLOCK * overlap(b.x, x1, k.x, k.x + k.w) * overlap(b.y, y1, k.y, k.y + k.h); });
    ctx.placed.forEach(function (k) { c += W_BADGE * overlap(b.x, x1, k.x, k.x + k.w) * overlap(b.y, y1, k.y, k.y + k.h); });
    return c;
  }

  /** 후보 자리(왼쪽 위 점) — 높이: 위 바깥 · 틀에 걸침(딱지 30%·60% 가 그림 안) · 그림 안 위 · 그림 안 아래,
      줄마다 왼쪽 끝 · 오른쪽 끝 · 가운데. 앞 후보일수록 조금 싸다(ORDER_COST). */
  function spots(r, w, h, g) {
    var xs = [r.x + g, r.x + r.w - w - g, r.x + (r.w - w) / 2], out = [];
    [r.y - h - g / 3, r.y - 0.7 * h, r.y - 0.4 * h, r.y + g, r.y + r.h - h - g].forEach(function (y) {
      xs.forEach(function (x) { out.push([x, y]); });
    });
    return out;
  }

  /** r 둘레(dx·dy 만큼 넓힌 칸)에 걸치는 것만 — 그림이 많아도 딱지마다 가까운 것만 견준다. */
  function near(list, r, dx, dy) {
    return list.filter(function (k) {
      var b = k.r || k;
      return b.x < r.x + r.w + dx && b.x + b.w > r.x - dx && b.y < r.y + r.h + dy && b.y + b.h > r.y - dy;
    });
  }

  function place(pics, items, blocks, bounds) {
    var byId = {}, placed = [], out = {};
    var allPics = pics || [], allBlocks = blocks || [], bnd = bounds || { w: 1e9, h: 1e9 };
    allPics.forEach(function (p) { byId[p.id] = p; });
    (items || []).forEach(function (it) {
      var p = byId[it.id], g = it.g || 0;
      if (!p || !(it.fw > 0) || !(it.bh > 0)) { return; }
      var dx = it.fw + 2 * g, dy = it.bh + 2 * g, best = null;
      var ctx = { id: it.id, photo: !!it.photo, pics: near(allPics, p.r, dx, dy), blocks: near(allBlocks, p.r, dx, dy),
        placed: near(placed, p.r, dx, dy), bounds: bnd };
      var kinds = [{ w: it.fw, short: false }];
      if (it.sw > 0 && it.sw < it.fw) { kinds.push({ w: it.sw, short: true }); }
      kinds.forEach(function (k) {
        if (!k.short && kinds.length > 1 && it.fw > p.r.w) { return; }   // 그림 폭보다 긴 글은 짧은 글로
        var extra = (k.short ? SHORT_COST : 0) * it.fw * it.bh;
        spots(p.r, k.w, it.bh, g).forEach(function (s, n) {
          var b = { x: s[0], y: s[1], w: k.w, h: it.bh };
          var c = cost(b, ctx) + extra + n * ORDER_COST * it.fw * it.bh;
          if (!best || c < best.c) { best = { c: c, b: b, short: k.short }; }
        });
      });
      placed.push(best.b);
      out[it.id] = { x: Math.round(best.b.x), y: Math.round(best.b.y), w: best.b.w, h: best.b.h, short: best.short };
    });
    return out;
  }

  /** 한 방향 줄마다 이어진 잉크(진하기 LINE_D 이상)가 RUN 점을 넘으면 선으로 표시한다. at(줄, 자리) → 점 번호. */
  function markRuns(d, line, len, cnt, at) {
    for (var q = 0; q < cnt; q++) {
      var s = 0;
      for (var p = 0; p <= len; p++) {
        if (p < len && d[at(q, p)] >= LINE_D) { continue; }
        if (p - s > RUN) { for (var m = s; m < p; m++) { line[at(q, m)] = 1; } }
        s = p + 1;
      }
    }
  }

  /** 줄인 그림 RGBA → 잉크 지도 { w, h, v, t } — CELL×CELL 칸마다 가장 진한 점(밝기 170 이하 = 1, 투명 = 바탕).
      t = 글자 같은 잉크: 가로·세로로 길게 이어진 잉크(치수선·외곽선·빗금 판)를 뺀 나머지의 가장 진한 점. */
  function inkFromPixels(px, w, h) {
    if (!px || !(w > 0) || !(h > 0) || px.length < w * h * 4) { return null; }
    var gw = Math.ceil(w / CELL), gh = Math.ceil(h / CELL), v = [], t = [], d = [], line = [], n = w * h, k;
    for (k = 0; k < gw * gh; k++) { v.push(0); t.push(0); }
    for (k = 0; k < n; k++) {
      var a = px[k * 4 + 3] / 255;
      var lum = (px[k * 4] * 299 + px[k * 4 + 1] * 587 + px[k * 4 + 2] * 114) / 1000 * a + 255 * (1 - a);
      d.push(Math.min(1, Math.max(0, (255 - lum) / 85)));
      line.push(0);
    }
    markRuns(d, line, w, h, function (q, p) { return q * w + p; });   // 가로
    markRuns(d, line, h, w, function (q, p) { return p * w + q; });   // 세로
    for (var y = 0; y < h; y++) {
      var row = Math.floor(y / CELL) * gw;
      for (var x = 0; x < w; x++) {
        var c = row + Math.floor(x / CELL);
        k = y * w + x;
        if (d[k] > v[c]) { v[c] = d[k]; }
        if (!line[k] && d[k] > t[c]) { t[c] = d[k]; }
      }
    }
    return { w: gw, h: gh, v: v, t: t };
  }

  /** 불러온 그림(<img>·뒤집은 canvas) → 잉크 지도(그림에 붙여 한 번만). 아직 안 불러왔으면 null(다음에 다시 잰다). */
  function inkGrid(src) {
    if (!src) { return null; }
    if (src._dwsInk !== undefined) { return src._dwsInk || null; }
    var nw = src.naturalWidth || src.width, nh = src.naturalHeight || src.height;
    if (!nw || !nh) { return null; }
    var out = false;
    try {
      var f = Math.min(1, SIDE / Math.max(nw, nh));
      var w = Math.max(1, Math.round(nw * f)), h = Math.max(1, Math.round(nh * f));
      var cv = document.createElement('canvas');
      cv.width = w; cv.height = h;
      var c2 = cv.getContext('2d', { willReadFrequently: true });
      c2.fillStyle = '#ffffff';
      c2.fillRect(0, 0, w, h);
      c2.imageSmoothingEnabled = true;
      c2.imageSmoothingQuality = 'high';
      c2.drawImage(src, 0, 0, w, h);
      out = inkFromPixels(c2.getImageData(0, 0, w, h).data, w, h) || false;
    } catch (e) {
      out = false;   // 다른 출처 그림 등 읽지 못하면 가득 찬 것으로 본다
    }
    src._dwsInk = out;
    return out || null;
  }

  /** 딱지의 화면 크기 배율 — 줌 100% 이상은 1(늘 12px), 아래에서는 줌을 따라 줄되 MIN_SCALE 까지(wizard.css .dws-pbadge 와 같은 식). */
  function badgeScale(zoom) { return (zoom > 0 && zoom < 1) ? Math.max(MIN_SCALE, zoom) : 1; }

  window.FomsPartBadgeSpot = { place: place, inkFromPixels: inkFromPixels, inkGrid: inkGrid, inkCover: inkCover, badgeScale: badgeScale };
})();
