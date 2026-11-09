/**
 * 탭별 글자 크기(2026-11-09 사용자 — "각 탭마다, 수집 탭과 마찬가지로").
 * 첫 그림 전 적용 · 탭 → 저장 열쇠는 layout_head boot 의 window.fomsFsKey / window.fomsApplyFs 가 맡는다.
 * 여기서는 제목 줄 조절기(− 100% +) 누름 → 저장 → 다시 붙이기, ERP 탭 전환(프래그먼트 교체) 뒤 다시 붙이기.
 * 단계 70~150% 를 10% 씩(11-09 사용자: 100% 아래로도 · 10 단위로).
 */
(function () {
  'use strict';

  var STEPS = [0.7, 0.8, 0.9, 1, 1.1, 1.2, 1.3, 1.4, 1.5];
  var root = document.documentElement;

  function current() {
    var fs = parseFloat(root.getAttribute('data-foms-fs') || '');
    return STEPS.indexOf(fs) >= 0 ? fs : 1;
  }

  function render() {
    var fs = current();
    var idx = STEPS.indexOf(fs);
    var ctls = document.querySelectorAll('[data-foms-fs-ctl]');
    for (var i = 0; i < ctls.length; i++) {
      var now = ctls[i].querySelector('[data-foms-fs-reset]');
      if (now) now.textContent = Math.round(fs * 100) + '%';
      var down = ctls[i].querySelector('[data-foms-fs-step="-1"]');
      var up = ctls[i].querySelector('[data-foms-fs-step="1"]');
      if (down) down.disabled = idx <= 0;
      if (up) up.disabled = idx >= STEPS.length - 1;
    }
  }

  function save(fs) {
    var key = root.getAttribute('data-foms-fs-key');
    if (!key) return;
    try {
      if (fs === 1) localStorage.removeItem(key);
      else localStorage.setItem(key, String(fs));
    } catch (e) { /* 저장 막힘 — 이번 화면에만 적용 */ }
  }

  function reapply(href) {
    if (typeof window.fomsApplyFs === 'function') window.fomsApplyFs(href);
    render();
  }

  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest ? e.target.closest('[data-foms-fs-step],[data-foms-fs-reset]') : null;
    if (!t) return;
    e.preventDefault();
    var next = 1;
    if (!t.hasAttribute('data-foms-fs-reset')) {
      var idx = STEPS.indexOf(current()) + parseInt(t.getAttribute('data-foms-fs-step'), 10);
      next = STEPS[Math.max(0, Math.min(STEPS.length - 1, idx))];
    }
    save(next);
    reapply();
  });

  // ERP 탭 전환은 본문만 갈아 끼운다(주소는 pushState) — 새 탭의 값으로 다시 붙인다.
  document.addEventListener('foms:main-content-swapped', function (e) {
    reapply(e && e.detail && e.detail.url ? e.detail.url : undefined);
  });
  window.addEventListener('popstate', function () { reapply(); });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render);
  } else {
    render();
  }
})();
