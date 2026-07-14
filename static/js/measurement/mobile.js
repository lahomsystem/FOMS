(function () {
    'use strict';

    // 실측 모바일 카드의 주소/연락처/담당 '빠른 수정' UI는 제거됨 — 편집은 데스크톱 인라인/상세로 일원화.
    // 이 모듈은 검색 카드 딥링크(?focus_order=)로 진입 시 해당 카드로 스크롤·하이라이트하는 책임만 남는다.
    function initMeasurementMobile() {
        var root = document.querySelector('.erp-measurement-dashboard[data-erp-mobile-v2="true"]');
        if (!root) return;

        var focusOrder = new URLSearchParams(window.location.search).get('focus_order');
        if (!focusOrder) return;

        var focusCard = root.querySelector('[data-measurement-mobile-order-id="' + focusOrder + '"]');
        if (!focusCard) return;

        window.requestAnimationFrame(function () {
            focusCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
            focusCard.classList.add('is-focused');
            window.setTimeout(function () {
                focusCard.classList.remove('is-focused');
            }, 2400);
        });
    }

    // entry 동적 로드 대응 readyState 분기 + fragment 스왑 재초기화(리스너 root 스코프라 per-DOM).
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMeasurementMobile);
    } else {
        initMeasurementMobile();
    }
    if (!window.__FOMS_MEAS_MOBILE_BOUND) {
        window.__FOMS_MEAS_MOBILE_BOUND = true;
        document.addEventListener('foms:erp-shell-fragment-swapped', initMeasurementMobile);
    }
})();
