/**
 * 화면 크기 손잡이(2026-11-09 사용자) — 70~130%, 10% 단계.
 * 첫 그림 전 배율은 layout_head 의 boot 가 붙인다(같은 저장 열쇠 html[data-foms-ui-zoom-key]).
 * 여기서는 단추 누름 → html 배율 · 저장 · 화면의 모든 손잡이 숫자를 함께 바꾼다.
 */
(function () {
  'use strict';

  var MIN = 70;
  var MAX = 130;
  var STEP = 10;
  var root = document.documentElement;

  function currentPct() {
    var z = parseFloat(root.getAttribute('data-foms-ui-zoom') || '');
    return z > 0 ? Math.round(z * 100) : 100;
  }

  function apply(pct) {
    pct = Math.max(MIN, Math.min(MAX, Math.round(pct / STEP) * STEP));
    if (pct === 100) {
      root.removeAttribute('data-foms-ui-zoom');
      root.style.removeProperty('--foms-ui-zoom');
    } else {
      root.setAttribute('data-foms-ui-zoom', String(pct / 100));
      root.style.setProperty('--foms-ui-zoom', String(pct / 100));
    }
    var key = root.getAttribute('data-foms-ui-zoom-key');
    if (key) {
      try {
        if (pct === 100) localStorage.removeItem(key);
        else localStorage.setItem(key, String(pct));
      } catch (e) { /* 저장 막힘 — 이번 화면에만 적용 */ }
    }
    render();
    try {
      window.dispatchEvent(new Event('resize'));
    } catch (e) { /* 옛 브라우저 */ }
  }

  function render() {
    var pct = currentPct();
    var groups = document.querySelectorAll('[data-foms-ui-zoom-ctl]');
    for (var i = 0; i < groups.length; i++) {
      var g = groups[i];
      var now = g.querySelector('[data-foms-ui-zoom-reset]');
      if (now) now.textContent = pct + '%';
      var down = g.querySelector('[data-foms-ui-zoom-step="-1"]');
      var up = g.querySelector('[data-foms-ui-zoom-step="1"]');
      if (down) down.disabled = pct <= MIN;
      if (up) up.disabled = pct >= MAX;
    }
  }

  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest ? e.target.closest('[data-foms-ui-zoom-step],[data-foms-ui-zoom-reset]') : null;
    if (!t) return;
    e.preventDefault();
    if (t.hasAttribute('data-foms-ui-zoom-reset')) {
      apply(100);
      return;
    }
    apply(currentPct() + STEP * parseInt(t.getAttribute('data-foms-ui-zoom-step'), 10));
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render);
  } else {
    render();
  }
})();
