/* 생산 작업 시트(/erp/production/sheet/<id>) 큰 도면 칸 — 손가락으로 옆으로 밀어 앞 · 다음 도면(사장님 2026-11-27 "이 화면에서도 도면 스와이프 해서 넘길 수 있게").
 * 넘기기는 이미 있는 [앞] [다음] 단추를 누른다(foms-production-sheet-page.js 의 showDrawing 그대로 — 머리 글 · 작은 그림 줄 · 고른 표시 ·
 * 끝에서 처음으로 도는 것까지 단추와 같다). 단추는 도면이 2장 이상일 때만 그려지므로 1장이면 아무 일 없다.
 * 판정 값은 공용 GlobalImageViewer(static/js/runtime/layout-scripts-core.js) 넘김과 같다: 가로 56px 넘게 · 가로가 세로의 1.2배 넘게,
 * 또는 250ms 안의 빠른 튕김 30px. 이 칸은 화면 굴림과 함께 있어 튕김도 가로가 세로의 1.2배 넘을 때만(세로 굴림을 넘김으로 읽지 않게).
 * 두 손가락(확대)이 한 번이라도 닿은 손짓 · 화면 확대 중(visualViewport.scale > 1)에는 넘기지 않는다. 이 칸에는 그림 확대가 없다(두드리면 크게 보기).
 * 민 뒤 따라오는 click 은 삼킨다(크게 보기가 열리지 않게). 그냥 두드리면 지금처럼 크게 보기.
 * touch* 만 쓴다(마우스 · PC 창은 그대로). 세로 굴림은 살리고 가로 밀기를 브라우저가 가져가지 않게 칸에 touch-action: pan-y pinch-zoom(sheet.css).
 * 셸 조각 교체로 다시 실행돼도 칸마다 한 번(__FOMS_PROD_SHEET_SWIPE_BOUND.el), 문서 리스너도 한 번(.doc). */
(function () {
  'use strict';

  var SWIPE_MIN = 56;
  var FLICK_MIN = 30;
  var FLICK_MS = 250;
  var RATIO = 1.2;
  var SWALLOW_MS = 600;

  var bound = window.__FOMS_PROD_SHEET_SWIPE_BOUND = window.__FOMS_PROD_SHEET_SWIPE_BOUND || {};

  function pageZoomed() {
    var vv = window.visualViewport;
    return !!(vv && vv.scale > 1.01);
  }

  function bindStage(stage) {
    var page = stage.closest('[data-foms-prod-sheet-page]');
    if (!page) { return; }
    var s = { on: false, multi: false, x: 0, y: 0, lx: 0, ly: 0, at: 0, swallowUntil: 0 };

    function navButton(step) {
      return page.querySelector(step > 0 ? '[data-foms-sheet-dwg-next]' : '[data-foms-sheet-dwg-prev]');
    }

    stage.addEventListener('touchstart', function (e) {
      if (!e.touches || !e.touches.length) { return; }
      if (e.touches.length >= 2) { s.multi = true; s.on = false; return; }
      var t = e.touches[0];
      s.on = true; s.multi = false;
      s.x = t.clientX; s.y = t.clientY; s.lx = t.clientX; s.ly = t.clientY; s.at = Date.now();
    }, { passive: true });

    stage.addEventListener('touchmove', function (e) {
      if (!s.on || !e.touches) { return; }
      if (e.touches.length !== 1) { s.multi = true; s.on = false; return; }
      s.lx = e.touches[0].clientX; s.ly = e.touches[0].clientY;
    }, { passive: true });

    stage.addEventListener('touchend', function (e) {
      var left = e.touches ? e.touches.length : 0;
      if (left > 0) { return; }
      var was = s.on && !s.multi;
      s.on = false; s.multi = false;
      if (!was || pageZoomed()) { return; }
      var ct = e.changedTouches && e.changedTouches[0];
      if (ct) { s.lx = ct.clientX; s.ly = ct.clientY; }
      var dx = s.lx - s.x;
      var dy = s.ly - s.y;
      var ax = Math.abs(dx);
      var dt = Date.now() - s.at;
      var swipe = ax > SWIPE_MIN && ax > Math.abs(dy) * RATIO;
      var flick = dt < FLICK_MS && ax > FLICK_MIN && ax > Math.abs(dy) * RATIO;
      if (!swipe && !flick) { return; }
      s.swallowUntil = Date.now() + SWALLOW_MS;
      if (e.cancelable) { e.preventDefault(); } // 민 손짓의 click 을 브라우저가 만들지 않게
      var btn = navButton(dx < 0 ? 1 : -1);
      if (btn) { btn.click(); }
    }, { passive: false });

    stage.addEventListener('touchcancel', function () { s.on = false; s.multi = false; }, { passive: true });

    // 민 뒤 따라오는 click — 크게 보기(sheet-page.js 의 page 위임)까지 가지 않게 칸에서 먼저 받아 삼킨다
    stage.addEventListener('click', function (e) {
      if (Date.now() > s.swallowUntil) { return; }
      s.swallowUntil = 0;
      e.preventDefault();
      e.stopPropagation();
    }, true);
  }

  function bindAll() {
    var stage = document.querySelector('[data-foms-prod-sheet-page] [data-foms-sheet-dwg-open]');
    if (!stage || bound.el === stage || typeof stage.closest !== 'function') { return; }
    bound.el = stage;
    bindStage(stage);
  }

  bindAll();
  if (!bound.doc) {
    bound.doc = true;
    document.addEventListener('foms:erp-shell-fragment-swapped', bindAll);
    document.addEventListener('foms:main-content-swapped', bindAll);
  }
})();
