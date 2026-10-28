/**
 * 도면 마법사 — 줄여 그린 그림을 고운 필터로 그린다(Chrome · Edge).
 *
 * 2026-10-28 사용자 보고 '컴퍼넌트를 줄이면 화질이 떨어진다'(병렬 조사 · 총괄 판정 1번):
 * Konva.Image 는 원본 그림을 그릴 때마다 drawImage 로 줄이고 imageSmoothingQuality 를 정하지 않아 캔버스 기본 'low' 가 쓰인다.
 * GPU 캔버스의 Chromium 은 'low' 로 33% 밑까지 줄이면 1px 치수선이 끊기거나 겹치고 빗금이 물결무늬가 되며 숫자 획이 깨진다
 * (합성 도면 1800×1200 → 480×320: PSNR 31.97 → 35.03dB, 뒤집은 그림 23.9 → 35dB, 20장 다시 그리기 0.34 → 0.29ms).
 * 그림 노드에 이 sceneFunc 를 주면 그 그림을 그리는 동안만 'high' 로 바꾸고 되돌린다(캔버스 크기 · pixelRatio 가 바뀌면 상태가 풀려
 * 그릴 때마다 넣는다). 클릭 판정은 Konva.Image 의 사각형 hitFunc 그대로라 영향이 없다.
 * - node.image() 는 원본 그대로 둔다 — 치수 글자 높이(part-textsize) · 빗금(hatchOf) · 딱지(part-badges) · api.image 가 원본을 읽는다.
 * - Chrome · Edge 만. Safari/iPad · Firefox 는 'high' 가 없거나 너무 느려(WebKit 그림 한 장 다시 그리기 100ms 넘게) 그대로 둔다.
 * - PNG 내보내기(toCanvas pixelRatio 2)도 같은 sceneFunc 로 그려 함께 고와진다(크기 · 저장 방식 그대로).
 *
 * window.FomsImageSmooth = { sceneFunc(ctx, shape), enabled }
 */
(function () {
  'use strict';
  if (window.FomsImageSmooth) { return; }

  var UA = (window.navigator && window.navigator.userAgent) || '';
  var enabled = /(Chrome|Chromium|Edg)\//.test(UA) && !/(CriOS|EdgiOS|FxiOS)\//.test(UA);

  function sceneFunc(ctx, shape) {
    var raw = enabled && ctx ? ctx._context : null, prev = raw ? raw.imageSmoothingQuality : null;
    if (raw) { raw.imageSmoothingQuality = 'high'; }
    window.Konva.Image.prototype._sceneFunc.call(shape, ctx);
    if (raw) { raw.imageSmoothingQuality = prev; }
  }

  window.FomsImageSmooth = { sceneFunc: sceneFunc, enabled: enabled };
})();
