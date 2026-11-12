/**
 * 태블릿 가로 출고 탭 — 위 줄 [협력사 희망 N] 단추로 협력사 희망 판을 위에서 내려오는 서랍으로 여닫기
 * (설계서 docs/specs/2026-11-09-tablet-production-ui_SPEC.md §14.8 · 시안 안 22).
 * 판은 한 벌(partner_request_board.html)이다 — 태블릿 코호트 CSS 가 평소 숨기고, 출고 뿌리(.erp-dashboard-shipment)에
 * is-prb-drop-open 이 붙으면 위 줄 바로 아래에 고정 서랍 + 뒤 막으로 보인다(partner-request-board.css). 표는 밀리지 않는다.
 * 닫기 = 단추 다시 · 막 · [닫기 ▴] · Esc(정하기 창이 열려 있으면 Esc 는 창 먼저). 열림은 기억하지 않는다(늘 닫힌 채 시작).
 * 서랍 자리는 열 때 위 줄 아래끝 · 뿌리 폭을 재서 CSS 변수로 넘긴다 — 화면 크기 배율(html zoom)이 붙으면
 * rect 는 보이는 px 이고 CSS 는 배율 전 px 라 배율로 나눈다. 실리는 곳 = shipment-entry.js CHAIN(문서 위임 싱글턴).
 */
(function () {
  'use strict';
  if (window.__FOMS_PRB_DROP_BOUND) return;
  window.__FOMS_PRB_DROP_BOUND = true;

  var OPEN = 'is-prb-drop-open';

  function root() { return document.querySelector('.erp-dashboard-shipment'); }
  function uiZoom() {
    var z = typeof window.fomsUiZoom === 'function' ? Number(window.fomsUiZoom()) : 1;
    return z > 0 ? z : 1;
  }
  function isOpen() { var r = root(); return !!r && r.classList.contains(OPEN); }

  function place(r) {
    var z = uiZoom(), bar = r.querySelector('.foms-ship-pcbar'), box = r.getBoundingClientRect();
    var top = bar ? bar.getBoundingClientRect().bottom : box.top;
    r.style.setProperty('--prb-drop-top', Math.max(0, top) / z + 'px');
    r.style.setProperty('--prb-drop-left', box.left / z + 'px');
    r.style.setProperty('--prb-drop-width', box.width / z + 'px');
  }

  function setOpen(open) {
    var r = root();
    if (!r) return;
    if (open) place(r);
    r.classList.toggle(OPEN, open);
    var btns = document.querySelectorAll('[data-prb-drop-toggle]');
    for (var i = 0; i < btns.length; i++) btns[i].setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  document.addEventListener('click', function (ev) {
    var t = ev.target;
    if (!t || !t.closest) return;
    if (t.closest('[data-prb-drop-toggle]')) return setOpen(!isOpen());
    if (t.closest('[data-prb-drop-scrim], [data-prb-drop-close]')) setOpen(false);
  });
  // 먼저(capture) 본다 — 정하기 창(#prb-pop)이 열려 있으면 이번 Esc 는 판 JS 가 창만 닫게 둔다.
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && isOpen() && !document.getElementById('prb-pop')) setOpen(false);
  }, true);
  window.addEventListener('resize', function () { var r = root(); if (r && isOpen()) place(r); });
  // 셸 조각이 바뀌면 새 뿌리는 닫힌 채다 — 단추 표시만 맞춘다.
  document.addEventListener('foms:erp-shell-fragment-swapped', function () { setOpen(false); });
})();
