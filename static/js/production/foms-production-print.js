/* 작업지시서 인쇄 단추(F8, 2026-11-09). [인쇄] = window.print(). 주소에 ?auto=1 이면 그림이 다 뜬 뒤 바로 인쇄 창. */
(function () {
  'use strict';
  var btn = document.querySelector('[data-foms-print]');
  if (btn) { btn.addEventListener('click', function () { window.print(); }); }
  if (/[?&]auto=1\b/.test(window.location.search)) {
    window.addEventListener('load', function () { window.setTimeout(function () { window.print(); }, 300); });
  }
})();
