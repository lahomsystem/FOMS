/**
 * 도면 마법사 — 그림 속 치수 글자 높이 재기(자동 배치가 글자를 읽을 수 있는 크기로 놓으려고 쓴다).
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.2 (다 안 들어가면 더 줄이지 않고 나누기 제안)
 * - 글자 높이 = 작은 잉크 덩어리(숫자 꼴: 세로가 긴 작은 덩어리) 높이의 중앙값, 원본 픽셀 단위.
 * - 그림을 긴 변 800px 이하로 줄여서 잰다(한 장 50ms 안). 줄인 만큼 되돌려 원본 픽셀로 돌려준다.
 * - 숫자 꼴 덩어리가 3개 미만이면 0(모름) — 자동 배치는 그 그림의 글자 크기를 따지지 않는다.
 *
 * window.FomsPartTextSize = { fromPixels(rgba, w, h, scale) → 글자 높이|0, fromImage(img) → 글자 높이|0, MAX_SIDE }
 *   rgba  : 줄인 그림의 RGBA 바이트(Uint8ClampedArray·Buffer 등), w·h 는 줄인 크기
 *   scale : 줄인 비율(줄인 크기 ÷ 원본 크기, 1 이하)
 */
(function () {
  'use strict';
  if (window.FomsPartTextSize) { return; }

  var MAX_SIDE = 800;
  var DARK = 140;   // 줄이면 가는 획이 옅어진다 — 원본 기준 110 보다 조금 너그럽게

  function isInk(r, g, b, a) {
    if (a < 128) { return false; }   // 투명 = 바탕
    return (r + g + b) / 3 < DARK || (r > 150 && g < 90 && b < 90) || (b > 150 && r < 90 && g < 120);
  }

  /** 줄인 그림 픽셀 → 원본 픽셀 단위 글자 높이(모르면 0). 4방향 연결 덩어리만 센다. */
  function fromPixels(px, w, h, scale) {
    var f = (scale > 0 && scale <= 1) ? scale : 1;
    var n = w * h;
    if (!px || !(n > 0) || px.length < n * 4) { return 0; }
    var ink = new Uint8Array(n), i, j;
    for (i = 0, j = 0; i < n; i++, j += 4) {
      if (isInk(px[j], px[j + 1], px[j + 2], px[j + 3])) { ink[i] = 1; }
    }
    // 원본 기준 숫자 꼴: 높이 8~60, 폭 3~45, 점 15개 이상, 세로 ≥ 가로 × 0.9 — 줄인 비율만큼 줄여 본다
    var hMin = Math.max(2, 8 * f), hMax = 60 * f, wMin = Math.max(1, 3 * f), wMax = 45 * f;
    var nMin = Math.max(3, 15 * f * f);
    var stack = new Int32Array(n), heights = [];
    for (var p = 0; p < n; p++) {
      if (!ink[p]) { continue; }
      ink[p] = 0;
      var sp = 0, cnt = 0, x0 = p % w, x1 = x0, y0 = (p - x0) / w, y1 = y0;
      stack[sp++] = p;
      while (sp) {
        var q = stack[--sp], qx = q % w, qy = (q - qx) / w;
        cnt++;
        if (qx < x0) { x0 = qx; } else if (qx > x1) { x1 = qx; }
        if (qy < y0) { y0 = qy; } else if (qy > y1) { y1 = qy; }
        if (qx > 0 && ink[q - 1]) { ink[q - 1] = 0; stack[sp++] = q - 1; }
        if (qx < w - 1 && ink[q + 1]) { ink[q + 1] = 0; stack[sp++] = q + 1; }
        if (qy > 0 && ink[q - w]) { ink[q - w] = 0; stack[sp++] = q - w; }
        if (qy < h - 1 && ink[q + w]) { ink[q + w] = 0; stack[sp++] = q + w; }
      }
      var bh = y1 - y0 + 1, bw = x1 - x0 + 1;
      if (bh >= hMin && bh <= hMax && bw >= wMin && bw <= wMax && cnt >= nMin && bh >= bw * 0.9) { heights.push(bh); }
    }
    if (heights.length < 3) { return 0; }
    heights.sort(function (a, b) { return a - b; });
    return Math.round(heights[heights.length >> 1] / f * 10) / 10;
  }

  /** 불러온 그림(<img>·canvas) 한 장 → 글자 높이(원본 픽셀, 모르면 0). 흰 바탕에 그려 투명 PNG 도 같게 읽는다. */
  function fromImage(img) {
    try {
      var nw = img.naturalWidth || img.width, nh = img.naturalHeight || img.height;
      if (!nw || !nh) { return 0; }
      var f = Math.min(1, MAX_SIDE / Math.max(nw, nh));
      var w = Math.max(1, Math.round(nw * f)), h = Math.max(1, Math.round(nh * f));
      var canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = h;
      var ctx = canvas.getContext('2d', { willReadFrequently: true });
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, w, h);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(img, 0, 0, w, h);
      return fromPixels(ctx.getImageData(0, 0, w, h).data, w, h, w / nw);
    } catch (e) {
      return 0;   // 다른 출처 그림 등 읽지 못하면 모름
    }
  }

  window.FomsPartTextSize = { fromPixels: fromPixels, fromImage: fromImage, MAX_SIDE: MAX_SIDE };
})();
