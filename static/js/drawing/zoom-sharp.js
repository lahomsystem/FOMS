/**
 * 도면 마법사 — 확대해도 또렷하게: 화면 배율에 맞춰 그림판(Konva 캔버스) 해상도를 올린다.
 *
 * 2026-10-28 사용자 '150% 키우면 흐린거 고쳐'(병렬 조사 · 총괄 판정 2번):
 * 배율은 .dws-stage 의 CSS transform(scale) 이라 Konva 캔버스는 처음 잡은 devicePixelRatio 해상도 그대로 늘어나 흐려진다
 * (실험: 25% 로 줄인 그림을 200% 로 보면 SSIM 0.778 → 해상도를 맞추면 0.958). 배율이 바뀌고 0.15초 쉬면 레이어 캔버스
 * pixelRatio 를 devicePixelRatio × 배율로 바꾸고 바로 다시 그린다. 모니터를 옮겨 devicePixelRatio 가 바뀌어도 다시 맞춘다.
 * - 100% 이하는 devicePixelRatio 그대로(더 낮추면 오히려 나빠진다 — 35.70 → 31.76dB). 위 한도 3:
 *   1478×1040 스테이지면 캔버스 약 55MB. 배율을 다시 줄이면 해상도도 내려 메모리를 돌려준다.
 * - 0.25 단위로 올려 잡아(1.1배 → 1.25) 작은 배율 변화마다 캔버스를 새로 만들지 않는다.
 * - Konva 좌표 · 클릭 판정(hitCanvas pixelRatio 1) · PNG 내보내기(toCanvas 가 pixelRatio 2 캔버스를 따로 만든다)는 그대로다.
 *
 * window.FomsZoomSharp = { attach(stage) → { zoom(z), apply() }, target(zoom, dpr), CAP, WAIT }
 */
(function () {
  'use strict';
  if (window.FomsZoomSharp) { return; }

  var CAP = 3, WAIT = 150, STEP = 4;

  function target(zoom, dpr) {
    var base = dpr > 0 ? dpr : 1;
    if (!(zoom > 1)) { return base; }
    return Math.max(base, Math.min(CAP, Math.ceil(base * zoom * STEP) / STEP));
  }

  /* devicePixelRatio 가 바뀌면(모니터 옮김 · 브라우저 확대) 한 번 알리고 새 값으로 다시 건다. */
  function watchDpr(cb) {
    if (!window.matchMedia) { return; }
    var mq = window.matchMedia('(resolution: ' + (window.devicePixelRatio || 1) + 'dppx)');
    function on() {
      if (mq.removeEventListener) { mq.removeEventListener('change', on); } else if (mq.removeListener) { mq.removeListener(on); }
      cb();
      watchDpr(cb);
    }
    if (mq.addEventListener) { mq.addEventListener('change', on); } else if (mq.addListener) { mq.addListener(on); }
  }

  function attach(stage) {
    var zoom = 1, timer = null;
    function apply() {
      timer = null;
      var pr = target(zoom, window.devicePixelRatio);
      if (stage.bufferCanvas && stage.bufferCanvas.getPixelRatio() !== pr) { stage.bufferCanvas.setPixelRatio(pr); }   // 반투명 채움+선 도형용
      stage.getLayers().forEach(function (layer) {
        var cv = layer.getCanvas();
        if (cv.getPixelRatio() === pr) { return; }
        cv.setPixelRatio(pr);
        layer.draw();   // 크기를 바꾸면 캔버스가 비워진다 — 다음 프레임을 기다리지 않고 바로 그려 깜빡이지 않게
      });
    }
    function later() { clearTimeout(timer); timer = setTimeout(apply, WAIT); }
    watchDpr(later);
    return { zoom: function (z) { zoom = z; later(); }, apply: apply };
  }

  window.FomsZoomSharp = { attach: attach, target: target, CAP: CAP, WAIT: WAIT };
})();
