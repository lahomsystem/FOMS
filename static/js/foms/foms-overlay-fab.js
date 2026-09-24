/**
 * 아래에서 올라오는 창(Bootstrap offcanvas)·팝업(modal)이 열린 동안 html 에 foms-overlay-open 을 단다.
 * foms-shell.css 가 이 표시로 + 버튼(.foms-shell-fab)을 숨긴다 — + 버튼이 창보다 위층이라 필터 창의
 * 날짜 칸을 가렸다(2026-09-24). 여러 창이 겹쳐 열려도 마지막 창이 닫힐 때만 표시를 뗀다.
 */
(function () {
    'use strict';
    if (window.__fomsOverlayFabBound) return;
    window.__fomsOverlayFabBound = true;

    var OPEN_SEL = '.offcanvas.show, .offcanvas.showing, .modal.show';

    function sync(opening) {
        var on = opening || !!document.querySelector(OPEN_SEL);
        document.documentElement.classList.toggle('foms-overlay-open', on);
    }

    ['show.bs.offcanvas', 'show.bs.modal'].forEach(function (name) {
        document.addEventListener(name, function () { sync(true); });
    });
    ['hidden.bs.offcanvas', 'hidden.bs.modal'].forEach(function (name) {
        document.addEventListener(name, function () { sync(false); });
    });
    // 화면 조각이 바뀌면(셸 이동) 열린 창이 사라졌을 수 있다.
    document.addEventListener('foms:erp-shell-fragment-swapped', function () { sync(false); });
})();
