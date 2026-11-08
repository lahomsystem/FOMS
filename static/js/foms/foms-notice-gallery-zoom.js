/**
 * FOMS 공지 사진 창 — 확대 · 옮기기 · 넘기기 손짓(foms-notice-gallery.js 가 쓴다, 2026-11-08).
 * 공용 사진 보기(GlobalImageViewer, layout-scripts-core.js)와 같은 손짓을 공지 사진 창에 붙인다.
 * 공용 사진 보기는 협력사 화면에 없고 공지 창보다 아래 층이라, 손짓만 따로 떼어 같은 느낌으로 만든다.
 *
 * - 사진 한 번 누르기 = 누른 자리 기준 2배. 확대된 채로 한 번 누르기 = 원래대로.
 * - 두 손가락 벌리기 · 오므리기 = 두 손가락 가운데 기준 1~4배. 1배까지 오므리면 원래대로.
 * - 확대된 채로 한 손가락 끌기 = 옮기기(사진이 화면 밖으로 다 나가지 않게 묶는다).
 * - 1배일 때 옆으로 밀기 = 앞 · 다음 사진(onSwipe). 사진 바깥 누르기 = 닫기(onOutside).
 * - 컴퓨터: 사진 누르기 = 2배 / 원래대로, 바퀴 = 확대 · 축소, 확대된 채로 끌기 = 옮기기.
 * 브라우저 자체 화면 확대는 무대(stage)의 touch-action: none(foms-notice.css)으로 막는다.
 */
(function () {
  'use strict';

  if (window.FomsNoticeGalleryZoom) return;

  var MAX = 4;
  var TAP_SCALE = 2;
  var SWIPE_MIN = 40;
  var TAP_MS = 300;
  var TAP_MOVE = 10;

  function attach(o) {
    var stage = o.stage;
    var img = o.img;
    var z = { scale: 1, tx: 0, ty: 0 };
    var t = null; // 손가락 상태
    var m = null; // 마우스 끌기
    var skipClick = false;

    function zoomed() { return z.scale > 1.01; }

    function paint() {
      img.style.transform = zoomed() ? 'translate(' + z.tx + 'px,' + z.ty + 'px) scale(' + z.scale + ')' : '';
      img.classList.toggle('is-zoomed', zoomed());
    }

    /** 옮긴 만큼을 사진이 무대 밖으로 다 나가지 않게 묶는다. */
    function clampPan() {
      var box = stage.getBoundingClientRect();
      var mx = Math.max(0, (img.offsetWidth * z.scale - box.width) / 2);
      var my = Math.max(0, (img.offsetHeight * z.scale - box.height) / 2);
      z.tx = Math.min(mx, Math.max(-mx, z.tx));
      z.ty = Math.min(my, Math.max(-my, z.ty));
    }

    function reset() {
      z.scale = 1;
      z.tx = 0;
      z.ty = 0;
      paint();
    }

    /** 화면의 한 점(누른 자리 · 두 손가락 가운데 · 마우스)이 손가락 밑에 그대로 남게 확대한다. */
    function zoomAt(next, cx, cy) {
      next = Math.min(MAX, Math.max(1, next));
      if (next <= 1.01) { reset(); return; }
      var box = stage.getBoundingClientRect();
      var fx = cx - (box.left + box.width / 2);
      var fy = cy - (box.top + box.height / 2);
      var ratio = next / z.scale;
      z.tx = fx - ratio * (fx - z.tx);
      z.ty = fy - ratio * (fy - z.ty);
      z.scale = next;
      clampPan();
      paint();
    }

    /** 누르기 하나 — 확대돼 있으면 원래대로, 사진이면 2배, 사진 바깥이면 닫기. */
    function tapAt(target, cx, cy) {
      if (zoomed()) reset();
      else if (target === img) zoomAt(TAP_SCALE, cx, cy);
      else if (o.onOutside) o.onOutside();
    }

    function gap(ts) { return Math.hypot(ts[0].clientX - ts[1].clientX, ts[0].clientY - ts[1].clientY); }
    function mid(ts) { return { x: (ts[0].clientX + ts[1].clientX) / 2, y: (ts[0].clientY + ts[1].clientY) / 2 }; }

    function oneFinger(p, target, after) {
      return { mode: 'one', x: p.clientX, y: p.clientY, tx: z.tx, ty: z.ty, at: Date.now(), moved: false, after: after, target: target };
    }

    // ---- 손가락 ----
    function onTouchStart(ev) {
      var ts = ev.touches;
      img.classList.add('is-gesture'); // 손가락을 바로 따라오게 움직임 효과를 끈다
      if (ts.length >= 2) {
        t = { mode: 'pinch', dist: gap(ts), base: z.scale };
        return;
      }
      if (ts.length === 1) t = oneFinger(ts[0], ev.target, false);
    }

    function onTouchMove(ev) {
      if (!t) return;
      var ts = ev.touches;
      if (t.mode === 'pinch' && ts.length >= 2 && t.dist) {
        var c = mid(ts);
        zoomAt(t.base * gap(ts) / t.dist, c.x, c.y);
        if (ev.cancelable) ev.preventDefault();
        return;
      }
      if (t.mode !== 'one' || ts.length !== 1) return;
      var dx = ts[0].clientX - t.x;
      var dy = ts[0].clientY - t.y;
      if (Math.abs(dx) > TAP_MOVE || Math.abs(dy) > TAP_MOVE) t.moved = true;
      if (zoomed()) {
        z.tx = t.tx + dx;
        z.ty = t.ty + dy;
        clampPan();
        paint();
      }
      if (ev.cancelable) ev.preventDefault();
    }

    function onTouchEnd(ev) {
      if (!t) return;
      if (ev.touches.length === 1) { t = oneFinger(ev.touches[0], null, true); return; } // 두 손가락 중 하나만 뗌 = 이어서 옮기기
      if (ev.touches.length) return;
      img.classList.remove('is-gesture');
      var s = t;
      var e = ev.changedTouches && ev.changedTouches[0];
      t = null;
      if (s.mode !== 'one' || s.after || !e) return;
      var dx = e.clientX - s.x;
      var dy = e.clientY - s.y;
      if (!s.moved && Date.now() - s.at < TAP_MS) {
        if (ev.cancelable) ev.preventDefault(); // 뒤따르는 click 으로 두 번 처리되지 않게
        tapAt(s.target, e.clientX, e.clientY);
        return;
      }
      if (!zoomed() && o.onSwipe && Math.abs(dx) >= SWIPE_MIN && Math.abs(dx) > Math.abs(dy)) o.onSwipe(dx < 0 ? 1 : -1);
    }

    stage.addEventListener('touchstart', onTouchStart, { passive: true });
    stage.addEventListener('touchmove', onTouchMove, { passive: false });
    stage.addEventListener('touchend', onTouchEnd, { passive: false });
    stage.addEventListener('touchcancel', function () { t = null; img.classList.remove('is-gesture'); });

    // ---- 마우스 ----
    stage.addEventListener('mousedown', function (ev) {
      skipClick = false;
      if (ev.button !== 0 || ev.target !== img || !zoomed()) return;
      ev.preventDefault();
      m = { x: ev.clientX, y: ev.clientY, tx: z.tx, ty: z.ty, moved: false };
      img.classList.add('is-gesture', 'is-dragging');
    });
    window.addEventListener('mousemove', function (ev) {
      if (!m) return;
      var dx = ev.clientX - m.x;
      var dy = ev.clientY - m.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) m.moved = true;
      z.tx = m.tx + dx;
      z.ty = m.ty + dy;
      clampPan();
      paint();
    });
    window.addEventListener('mouseup', function () {
      if (!m) return;
      skipClick = m.moved; // 끌기를 끝낸 click 은 누르기로 치지 않는다
      m = null;
      img.classList.remove('is-gesture', 'is-dragging');
    });
    stage.addEventListener('click', function (ev) {
      if (skipClick) { skipClick = false; return; }
      tapAt(ev.target, ev.clientX, ev.clientY);
    });
    stage.addEventListener('wheel', function (ev) {
      ev.preventDefault();
      zoomAt(z.scale * (ev.deltaY > 0 ? 0.9 : 1.1), ev.clientX, ev.clientY);
    }, { passive: false });

    return { reset: reset, zoomed: zoomed, zoomAt: zoomAt, tapAt: tapAt };
  }

  window.FomsNoticeGalleryZoom = { attach: attach };
})();
