/**
 * 태블릿 가로 출고 탭 — 왼쪽 "날짜별 남은 자수" 띠 여닫기 (2026-11-11 사용자 "단추로 여닫기").
 * 띠는 CSS 로 평소 숨김(깜박임 없음). 위 줄 단추(button[data-ship-cap-toggle])를 누르면 출고 뿌리
 * (.erp-dashboard-shipment)에 is-ship-cap-open 을 붙였다 뗀다. 열림 여부는 localStorage 한 값에 기억하고,
 * 저장 뒤 다시 받기 · 날짜 바꾸기 · 셸 조각 바뀜 뒤에도 다시 적용한다(문서 위임 + 싱글턴).
 * 저장소가 막혀도(사생활 보호 창 등) 이번 화면에서만 여닫힌다. 실리는 곳 = shipment-entry.js CHAIN.
 */
(function () {
  'use strict';
  if (window.__FOMS_SHIP_CAPSTRIP_BOUND) return;
  window.__FOMS_SHIP_CAPSTRIP_BOUND = true;

  var KEY = 'foms.shipment.capStripOpen';
  var memo = false;

  function readOpen() {
    try {
      memo = window.localStorage.getItem(KEY) === '1';
    } catch (e) { /* 저장소 막힘 — 이번 화면 값 그대로 */ }
    return memo;
  }

  function writeOpen(open) {
    memo = open;
    try {
      if (open) window.localStorage.setItem(KEY, '1');
      else window.localStorage.removeItem(KEY);
    } catch (e) { /* 저장소 막힘 — 이번 화면에서만 */ }
  }

  function apply(open) {
    var roots = document.querySelectorAll('.erp-dashboard-shipment');
    for (var i = 0; i < roots.length; i++) roots[i].classList.toggle('is-ship-cap-open', open);
    var btns = document.querySelectorAll('[data-ship-cap-toggle]');
    for (var j = 0; j < btns.length; j++) btns[j].setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  document.addEventListener('click', function (ev) {
    var btn = ev.target && ev.target.closest && ev.target.closest('[data-ship-cap-toggle]');
    if (!btn) return;
    var open = btn.getAttribute('aria-expanded') !== 'true';
    writeOpen(open);
    apply(open);
  });

  function sync() { apply(readOpen()); }
  document.addEventListener('foms:erp-shell-fragment-swapped', sync);
  document.addEventListener('foms:main-content-swapped', sync);
  sync();
})();
