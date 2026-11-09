/**
 * ERP 탭 줄(.erp-pro-nav)을 전역 메뉴 바로 밑에 붙이기 위해
 * 전역 메뉴 높이를 --foms-global-nav-sticky-h 로 넣는다(2026-11-04).
 * 전역 메뉴가 sticky 가 아니거나 숨겨져 있으면 0px.
 */
(function () {
    'use strict';

    function syncGlobalNavHeight() {
        var nav = document.querySelector('nav.layout-global-nav');
        var offset = 0;
        if (nav) {
            var navStyle = window.getComputedStyle(nav);
            if (navStyle.position === 'sticky' && navStyle.display !== 'none') {
                offset = nav.getBoundingClientRect().height || 0;
            }
        }
        // 화면 크기 배율(2026-11-09): rect 높이는 보이는 px, CSS 변수는 배율 전 px 다 — 나눠 넣는다.
        var uiZoom = window.fomsUiZoom ? window.fomsUiZoom() : 1;
        document.documentElement.style.setProperty('--foms-global-nav-sticky-h', Math.round(offset / uiZoom) + 'px');
    }

    function init() {
        syncGlobalNavHeight();
        window.addEventListener('resize', syncGlobalNavHeight, { passive: true });
        var nav = document.querySelector('nav.layout-global-nav');
        if (nav && window.ResizeObserver) {
            new ResizeObserver(syncGlobalNavHeight).observe(nav);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
