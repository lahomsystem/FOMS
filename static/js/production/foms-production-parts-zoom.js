/* 생산 파트 도면 '크게 보기' 그림 칸 — 그 자리에서 손가락 확대 · 이동(사장님 2026-11-27 "큰 화면에서 바로 확대": 두 번째 확대 화면 없앰).
 * 손맛은 공용 GlobalImageViewer(static/js/runtime/layout-scripts-core.js — 건드리지 않는다)를 따른다: 두 손가락 = 1~5배(손가락 가운데 기준) ·
 * 확대 뒤 한 손가락 = 이동(그림 가장자리까지만) · 두 번 두드리기 = 2.5배 ↔ 1배(두드린 곳 기준) · 휠 = 0.9 / 1.1배(마우스 자리 기준) · 끌기 = 이동.
 * 1배에서 한 손가락 밀기는 아무 일 없다(크게 보기는 넘김 손짓이 없고 ◀ ▶ 단추로 넘긴다). 한 번 두드리기도 아무 것도 열지 않는다.
 * 좌표: rect · clientX 는 보이는 px — style 에 넣을 때만 화면 크기 배율(window.fomsUiZoom)로 나눈다(전역 뷰어와 같은 식).
 * 경계는 1배 그림 크기(보이는 px)를 재 두고 계산한다 — 두 번 두드리기처럼 크게 뛰어도 그 배율 기준으로 바로 막힌다.
 * 그림 주소는 그대로(카드 data-view-url = /api/files/view 원본, 전역 뷰어가 받던 것과 같은 그림)라 확대해도 원본 화소다.
 * 뷰어(foms-production-parts-viewer.js)가 장을 열 · 넘길 · 닫을 때 reset(), 30초 받아 오기로 다시 그린 뒤 refit() 을 부른다.
 * 셸 조각 교체로 다시 실행된다: 그림 칸 리스너는 화면마다 한 번(__FOMS_PROD_PARTS_BOUND.zoom), 문서 · 창 리스너는 한 번(.zoomDoc).
 * 펜 기록 쓰는 상태(설계서 2026-11-28-production-pen-record §6-3): 손가락은 그대로 움직이기 · 키우기, 펜 · 마우스가 닿아 있는 동안(FomsPen.inking —
 * 손바닥 touch 가 같이 들어와도)은 손짓을 받지 않는다. 쓰는 층(SVG [data-pp-ink])은 그림과 같은 transform 을 따라간다. */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  var viewer = root && root.querySelector('[data-pp-viewer]');
  var stage = viewer && viewer.querySelector('[data-pp-v-zoom]');
  var img = stage && stage.querySelector('[data-pp-v-img]');
  if (!img) { return; }
  var bound = window.__FOMS_PROD_PARTS_BOUND = window.__FOMS_PROD_PARTS_BOUND || {};
  if (bound.zoom === root) { return; }
  bound.zoom = root;

  var MAX = 5;
  var TAP_ZOOM = 2.5;
  var s = { scale: 1, tx: 0, ty: 0, base: null, mode: '', startDist: 0, startScale: 1,
    panX: 0, panY: 0, baseTx: 0, baseTy: 0, downAt: 0, downX: 0, downY: 0, tapAt: 0, tapX: 0, tapY: 0 };

  function uiZoom() {
    var z = typeof window.fomsUiZoom === 'function' ? Number(window.fomsUiZoom()) || 1 : 1;
    return z > 0 ? z : 1;
  }
  // 원본 그림이 떠 있을 때만(파일 장 · 못 받은 그림 · 닫힌 창은 손짓을 받지 않는다) · 펜이 쓰는 중이면 받지 않는다
  function inking() { var p = window.FomsPen; return !!(p && p.inking && p.inking()); }
  function usable() {
    return !viewer.hidden && !img.hidden && !!img.getAttribute('src') && !stage.classList.contains('is-broken') && !inking();
  }
  function apply(anim) {
    stage.classList.toggle('is-anim', !!anim);
    stage.classList.toggle('is-zoomed', s.scale > 1);
    var z = uiZoom();
    img.style.transform = s.scale > 1 ? 'translate(' + (s.tx / z) + 'px, ' + (s.ty / z) + 'px) scale(' + s.scale + ')' : '';
    var ink = stage.querySelector('[data-pp-ink]');
    if (ink && ink.style) { ink.style.transform = img.style.transform; }
  }
  // 1배 그림 크기(보이는 px). 움직이는 중(is-anim)이면 끝 값으로 멈춘 뒤 잰다 — rect 는 transform 이 붙은 크기라 배율로 나눈다.
  function measure() {
    stage.classList.remove('is-anim');
    var r = img.getBoundingClientRect();
    s.base = { w: r.width / s.scale, h: r.height / s.scale };
  }
  function clamp() {
    if (s.scale <= 1) { s.scale = 1; s.tx = 0; s.ty = 0; return; }
    if (!s.base) { measure(); }
    var r = stage.getBoundingClientRect();
    var mx = Math.max(0, (s.base.w * s.scale - r.width) / 2);
    var my = Math.max(0, (s.base.h * s.scale - r.height) / 2);
    s.tx = Math.max(-mx, Math.min(mx, s.tx));
    s.ty = Math.max(-my, Math.min(my, s.ty));
  }
  // 손가락 가운데(또는 두드린 곳 · 마우스 자리) 아래 점이 그 자리에 머물게 — transform 기준점이 그림 가운데 = 칸 가운데
  function zoomTo(next, cx, cy, anim) {
    next = Math.max(1, Math.min(MAX, next));
    if (!s.base) { measure(); }
    var r = stage.getBoundingClientRect();
    var fx = cx - (r.left + r.width / 2);
    var fy = cy - (r.top + r.height / 2);
    var ratio = next / s.scale;
    s.tx = fx - ratio * (fx - s.tx);
    s.ty = fy - ratio * (fy - s.ty);
    s.scale = next <= 1.01 ? 1 : next;
    clamp();
    apply(anim);
  }
  function reset() {
    s.scale = 1; s.tx = 0; s.ty = 0; s.base = null; s.mode = ''; s.tapAt = 0; s.downAt = 0;
    apply(false);
  }
  // 창 크기 · 화면 돌림 · 단추 줄이 바뀐 뒤 — 1배 크기를 다시 재고 경계 안으로
  function refit() {
    s.base = null;
    if (s.scale <= 1 || !usable()) { return; }
    measure();
    clamp();
    apply(false);
  }

  function dist(a, b) {
    var dx = a.clientX - b.clientX;
    var dy = a.clientY - b.clientY;
    return Math.sqrt(dx * dx + dy * dy);
  }
  function startPan(x, y, mode) {
    s.mode = mode;
    s.panX = x; s.panY = y; s.baseTx = s.tx; s.baseTy = s.ty;
    stage.classList.remove('is-anim');
  }
  function panTo(x, y) {
    s.tx = s.baseTx + (x - s.panX);
    s.ty = s.baseTy + (y - s.panY);
    clamp();
    apply(false);
  }

  function onTouchStart(e) {
    if (!usable() || !e.touches || !e.touches.length) { return; }
    measure();
    if (e.touches.length >= 2) {
      s.mode = 'pinch'; s.downAt = 0;
      s.startDist = dist(e.touches[0], e.touches[1]);
      s.startScale = s.scale;
      return;
    }
    var t = e.touches[0];
    s.downAt = Date.now(); s.downX = t.clientX; s.downY = t.clientY;
    if (s.scale > 1.05) { startPan(t.clientX, t.clientY, 'pan'); } else { s.mode = ''; }
  }
  function onTouchMove(e) {
    if (!usable() || !e.touches) { return; }
    if (e.cancelable) { e.preventDefault(); } // 그림 칸 손짓은 이 칸 몫 — 화면 전체 확대 · 당겨 새로 고침과 싸우지 않는다
    if (s.mode === 'pinch' && e.touches.length >= 2) {
      var a = e.touches[0];
      var b = e.touches[1];
      if (s.startDist > 0) {
        zoomTo(s.startScale * (dist(a, b) / s.startDist), (a.clientX + b.clientX) / 2, (a.clientY + b.clientY) / 2, false);
      }
      return;
    }
    if (e.touches.length !== 1) { return; }
    var t = e.touches[0];
    if (s.mode !== 'pan' && s.scale > 1.05) { startPan(t.clientX, t.clientY, 'pan'); }
    if (s.mode === 'pan') { panTo(t.clientX, t.clientY); }
  }
  function isTap(e, left) {
    var ct = e.changedTouches && e.changedTouches[0];
    return !!(ct && left === 0 && s.mode !== 'pinch' && s.downAt && Date.now() - s.downAt < 250 &&
      Math.abs(ct.clientX - s.downX) < 20 && Math.abs(ct.clientY - s.downY) < 20);
  }
  function onTouchEnd(e) {
    if (!usable()) { return; }
    var left = e.touches ? e.touches.length : 0;
    if (isTap(e, left)) {
      var ct = e.changedTouches[0];
      var now = Date.now();
      if (now - s.tapAt < 300 && Math.abs(ct.clientX - s.tapX) < 40 && Math.abs(ct.clientY - s.tapY) < 40) {
        s.tapAt = 0; s.mode = '';
        if (e.cancelable) { e.preventDefault(); } // 두 번째 두드림의 click · 브라우저 두 번 두드리기 확대를 막는다
        zoomTo(s.scale > 1.05 ? 1 : TAP_ZOOM, ct.clientX, ct.clientY, true);
        return;
      }
      s.tapAt = now; s.tapX = ct.clientX; s.tapY = ct.clientY;
    }
    if (s.mode === 'pinch') {
      if (left >= 2) { return; }
      if (s.scale <= 1.05) { s.mode = ''; s.scale = 1; s.tx = 0; s.ty = 0; apply(false); return; }
      if (left === 1) { startPan(e.touches[0].clientX, e.touches[0].clientY, 'pan'); } else { s.mode = ''; }
      return;
    }
    if (left === 0) { s.mode = ''; }
  }
  // 시스템이 손짓을 가져감(전화 · 가장자리 뒤로 가기) — 상태만 되돌리고 확대는 그대로(전역 뷰어와 같음)
  function onTouchCancel() {
    s.mode = ''; s.downAt = 0;
    if (s.scale <= 1.05) { s.scale = 1; s.tx = 0; s.ty = 0; apply(false); }
  }

  function onWheel(e) {
    if (!usable()) { return; }
    e.preventDefault();
    zoomTo(s.scale * (e.deltaY > 0 ? 0.9 : 1.1), e.clientX, e.clientY, false);
  }
  function onMouseDown(e) {
    if (!usable() || e.button) { return; }
    e.preventDefault(); // 그림 끌어 옮기기(브라우저 기본)를 막는다
    if (s.scale <= 1) { return; }
    measure();
    startPan(e.clientX, e.clientY, 'drag');
  }
  function onMouseMove(e) {
    if (s.mode !== 'drag') { return; }
    if (e.preventDefault) { e.preventDefault(); }
    panTo(e.clientX, e.clientY);
  }
  function onMouseUp() { if (s.mode === 'drag') { s.mode = ''; } }

  stage.addEventListener('touchstart', onTouchStart, { passive: true });
  stage.addEventListener('touchmove', onTouchMove, { passive: false });
  stage.addEventListener('touchend', onTouchEnd, { passive: false });
  stage.addEventListener('touchcancel', onTouchCancel, { passive: true });
  stage.addEventListener('wheel', onWheel, { passive: false });
  stage.addEventListener('mousedown', onMouseDown);

  window.FomsPartsZoom = { reset: reset, refit: refit, onMouseMove: onMouseMove, onMouseUp: onMouseUp,
    state: function () { return { scale: s.scale, tx: s.tx, ty: s.ty }; } };
  if (!bound.zoomDoc) {
    bound.zoomDoc = true;
    document.addEventListener('mousemove', function (e) { var z = window.FomsPartsZoom; if (z) { z.onMouseMove(e); } });
    document.addEventListener('mouseup', function () { var z = window.FomsPartsZoom; if (z) { z.onMouseUp(); } });
    if (typeof window.addEventListener === 'function') { // 가로 · 세로 돌림도 resize 로 온다
      window.addEventListener('resize', function () { var z = window.FomsPartsZoom; if (z) { z.refit(); } });
    }
  }
})();
