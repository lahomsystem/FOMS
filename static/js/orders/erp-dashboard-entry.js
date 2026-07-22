/**
 * ERP 프로세스 대시보드: 외부 번들 순차 로드 (프래그먼트 HTML에는 마크업/데이터만 두고 스크립트 이중 실행 방지).
 * 최초 1회만 로드; 셸 탭 전환으로 HTML만 바뀔 때는 erp-shell + detail-dom의 foms:erp-shell-fragment-swapped 가 초기화.
 */
(function () {
  var CHAIN = [
    '/static/js/orders/order-detail-fragment.js?v=20260630c',
    '/static/js/orders/dashboard/erp-dashboard-core.js',
    '/static/js/orders/dashboard/erp-dashboard-gateway.js',
    '/static/js/orders/dashboard/erp-dashboard-attachments.js',
    '/static/js/orders/dashboard/erp-dashboard-drawing.js',
    '/static/js/orders/dashboard/erp-dashboard-quest.js',
    '/static/js/orders/dashboard/erp-dashboard-detail-dom.js?v=20260722a',
    '/static/js/orders/dashboard-notifications.js',
    // 태블릿 벌크 선택(프레임 12) — long-press 선택 모드 + contextual bar. 코호트(coarse
    // landscape)에서만 활성(파일 내부 게이트), 비-태블릿은 리스너 early-return. 동적 주입 =
    // 렌더 비차단(async=false, perf G1). 싱글턴 가드로 스왑 재kick 흡수.
    '/static/js/foms/tablet-bulk-select.js?v=20260713a'
  ];

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.async = false;
      s.onload = function () { resolve(); };
      s.onerror = function () { reject(new Error('Failed to load ' + src)); };
      document.head.appendChild(s);
    });
  }

  function hasDashboardRoot() {
    return !!(document.querySelector('#main-content .erp-dashboard') || document.querySelector('.erp-dashboard'));
  }

  function ensureBundle() {
    if (window.__fomsErpDashboardBundleLoaded) {
      return Promise.resolve();
    }
    if (window.__fomsErpDashboardBundlePromise) {
      return window.__fomsErpDashboardBundlePromise;
    }
    if (!hasDashboardRoot()) {
      return Promise.resolve();
    }
    window.__fomsErpDashboardBundlePromise = (async function () {
      for (var i = 0; i < CHAIN.length; i++) {
        await loadScript(CHAIN[i]);
      }
      window.__fomsErpDashboardBundleLoaded = true;
      window.__fomsErpDashboardBundlePromise = null;
    })().catch(function (err) {
      window.__fomsErpDashboardBundlePromise = null;
      console.error('[erp-dashboard-entry]', err);
      throw err;
    });
    return window.__fomsErpDashboardBundlePromise;
  }

  function kick() {
    ensureBundle();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', kick);
  } else {
    kick();
  }
  document.addEventListener('foms:erp-shell-fragment-swapped', kick);
})();
