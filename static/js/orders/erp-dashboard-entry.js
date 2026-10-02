/**
 * ERP 프로세스 대시보드: 외부 번들을 한꺼번에 받고 순서대로 실행 (프래그먼트 HTML에는 마크업/데이터만 두고 스크립트 이중 실행 방지).
 * 최초 1회만 로드; 셸 탭 전환으로 HTML만 바뀔 때는 erp-shell + detail-dom의 foms:erp-shell-fragment-swapped 가 초기화.
 */
(function () {
  var CHAIN = [
    '/static/js/orders/order-detail-fragment.js?v=20260804a',
    '/static/js/orders/dashboard/erp-dashboard-core.js?v=20260929h',
    '/static/js/orders/dashboard/erp-dashboard-gateway.js?v=20260929e',
    '/static/js/orders/dashboard/erp-dashboard-attachments.js?v=20260929h',
    '/static/js/orders/dashboard/erp-dashboard-drawing.js?v=20260929l',
    '/static/js/orders/dashboard/erp-dashboard-quest.js?v=20260930a',
    '/static/js/orders/dashboard/erp-dashboard-detail-dom.js?v=20261001a',
    '/static/js/orders/dashboard-notifications.js',
    // 태블릿 벌크 선택(프레임 12) — long-press 선택 모드 + contextual bar. 코호트(coarse
    // landscape)에서만 활성(파일 내부 게이트), 비-태블릿은 리스너 early-return. 동적 주입 =
    // 렌더 비차단(async=false, perf G1). 싱글턴 가드로 스왑 재kick 흡수.
    '/static/js/foms/tablet-bulk-select.js?v=20260713a'
  ];

  // 파일마다 로드 Promise 를 기억한다. 실패 뒤 다시 부를 때 이미 실행됐거나 받는 중인
  // 파일은 또 넣지 않는다 — 같은 파일이 두 번 실행되면 전역 리스너가 겹친다.
  var loads = window.__fomsErpDashboardChainLoads || (window.__fomsErpDashboardChainLoads = {});

  function loadScript(src) {
    if (loads[src]) {
      return loads[src];
    }
    loads[src] = new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      // async=false: 한꺼번에 넣어도 실행은 넣은 순서대로(다운로드만 병렬).
      s.async = false;
      s.onload = function () { resolve(); };
      s.onerror = function () {
        delete loads[src];
        if (s.parentNode) { s.parentNode.removeChild(s); }
        reject(new Error('Failed to load ' + src));
      };
      document.head.appendChild(s);
    });
    return loads[src];
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
    // 하나씩 기다리며 넣으면 파일 수만큼 왕복이 줄 선다(스테이징 콜드 9개 약 1.0초).
    // 한꺼번에 넣고 전부 끝나기를 기다린다. 실행 순서는 async=false 가 지킨다.
    window.__fomsErpDashboardBundlePromise = Promise.all(CHAIN.map(loadScript)).then(function () {
      window.__fomsErpDashboardBundleLoaded = true;
      window.__fomsErpDashboardBundlePromise = null;
    }).catch(function (err) {
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
