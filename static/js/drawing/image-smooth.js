/**
 * 도면 마법사 — 줄여 그린 그림을 곱게 그린다.
 *
 * 2026-10-28 사용자 보고 '컴퍼넌트를 줄이면 화질이 떨어진다'(병렬 조사 · 총괄 판정 1번):
 * Konva.Image 는 원본 그림을 그릴 때마다 drawImage 로 줄이고 imageSmoothingQuality 를 정하지 않아 캔버스 기본 'low' 가 쓰인다.
 * GPU 캔버스의 Chromium 은 'low' 로 33% 밑까지 줄이면 1px 치수선이 끊기거나 겹치고 빗금이 물결무늬가 되며 숫자 획이 깨진다
 * (합성 도면 1800×1200 → 480×320: PSNR 31.97 → 35.03dB, 뒤집은 그림 23.9 → 35dB, 20장 다시 그리기 0.34 → 0.29ms).
 * 같은 날 다시 보고 '위자드에 들어가서 줄이거나 늘이면 화질이 매우 저하'(끊긴 치수선 · 뭉개진 빗금): 'high' 는 그래픽 카드로 그리는
 * Chrome · Edge 캔버스에서만 먹는다 — 그래픽 카드 없이 그리는 캔버스(드라이버 차단 · 원격 데스크톱)와 Safari · Firefox 는 'low' 그대로라
 * 크게 줄이면 선이 끊긴다. 그래서 원본을 반씩 줄인 사다리(1/2 · 1/4 …)를 처음 필요할 때 만들어 두고 — 꼭 반씩 줄이면 네 점 평균이라
 * 어떤 필터로도 선이 끊기지 않는다 — 그릴 기기 픽셀 크기(캔버스 변환 배율 × 그림 크기: 화면 배율 · 크기 바꾸기 · PNG 내보내기 모두)
 * 이상인 칸 가운데 가장 작은 것으로 그린다. 마지막 줄임은 2배 안이다. Chrome · Edge 는 그 위에 'high' 도 그대로 쓴다.
 * - node.image() 는 원본 그대로 둔다(그리는 동안만 바꿔 그린다) — 치수 글자 높이(part-textsize) · 빗금(hatchOf) · 딱지(part-badges) · api.image 가 원본을 읽는다.
 * - 클릭 판정은 Konva.Image 의 사각형 hitFunc 그대로라 영향이 없다.
 *
 * window.FomsImageSmooth = { sceneFunc(ctx, shape), enabled, levelFor(src, needW) → { c, w, h }, STEP }
 */
(function () {
  'use strict';
  if (window.FomsImageSmooth) { return; }

  var UA = (window.navigator && window.navigator.userAgent) || '';
  var enabled = /(Chrome|Chromium|Edg)\//.test(UA) && !/(CriOS|EdgiOS|FxiOS)\//.test(UA);
  var STEP = 2;   // 원본이 그릴 크기의 이 배 넘게 크면 사다리에서 고른다

  function sizeOf(src) { return { w: src.naturalWidth || src.width || 0, h: src.naturalHeight || src.height || 0 }; }

  /** 그릴 기기 픽셀 폭 needW 이상인 사다리 칸 가운데 가장 작은 것(필요한 칸만 그때 만든다). 첫 칸 = 원본. */
  function levelFor(src, needW) {
    var s = sizeOf(src), lad = src._dwsLadder || (src._dwsLadder = [{ c: src, w: s.w, h: s.h }]), top = lad[lad.length - 1];
    while (top.w / 2 >= needW && top.w >= 4 && top.h >= 4) {
      var cv = document.createElement('canvas'), w = Math.round(top.w / 2), h = Math.round(top.h / 2);
      cv.width = w;
      cv.height = h;
      cv.getContext('2d').drawImage(top.c, 0, 0, w, h);
      top = { c: cv, w: w, h: h };
      lad.push(top);
    }
    for (var i = lad.length - 1; i > 0; i--) { if (lad[i].w >= needW) { return lad[i]; } }
    return lad[0];
  }

  function sceneFunc(ctx, shape) {
    var raw = ctx ? ctx._context : null, src = shape && shape.attrs ? shape.attrs.image : null, prev = raw ? raw.imageSmoothingQuality : null, lv = null;
    if (raw && src) {
      var t = raw.getTransform ? raw.getTransform() : null, s = sizeOf(src);
      var sx = t ? Math.sqrt(t.a * t.a + t.b * t.b) : 1, sy = t ? Math.sqrt(t.c * t.c + t.d * t.d) : 1;
      var needW = Math.max(shape.width() * sx, s.h ? shape.height() * sy * s.w / s.h : 0);
      if (needW > 0 && s.w > STEP * needW) { lv = levelFor(src, needW); }
    }
    if (raw && enabled) { raw.imageSmoothingQuality = 'high'; }
    if (lv && lv.c !== src) { shape.attrs.image = lv.c; }
    try {
      window.Konva.Image.prototype._sceneFunc.call(shape, ctx);
    } finally {
      if (lv) { shape.attrs.image = src; }
      if (raw && enabled) { raw.imageSmoothingQuality = prev; }
    }
  }

  window.FomsImageSmooth = { sceneFunc: sceneFunc, enabled: enabled, levelFor: levelFor, STEP: STEP };
})();
