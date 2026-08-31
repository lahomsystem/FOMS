/**
 * 실측 대시보드: 외부 번들 순차 로드 (프래그먼트 HTML에는 마크업/데이터만 두고 스크립트 이중 실행 방지).
 * 최초 1회만 로드; 셸 탭 전환으로 HTML만 바뀔 때는 각 모듈의 foms:erp-shell-fragment-swapped 리스너가 재초기화.
 *
 * 이 entry 태그는 fragment(dashboard_scripts.html) 안에 있어 탭 스왑마다 재실행될 수 있으나,
 * (1) 번들 로드는 __fomsMeasurementBundleLoaded singleton 으로 1회, (2) 스왑 리스너 등록은
 * __fomsMeasurementEntryInstalled 가드로 1회만 하여 listener 누적을 막는다.
 */
(function () {
  var MEAS_JS_V = '20260831a';
  var CHAIN = [
    '/static/js/runtime/common_utils.js?v=' + MEAS_JS_V,
    '/static/js/measurement/dashboard.js?v=' + MEAS_JS_V,
    '/static/js/measurement/mobile.js?v=' + MEAS_JS_V,
    '/static/js/runtime/column-resizer.js?v=' + MEAS_JS_V,
    '/static/js/measurement/dashboard-columns.js?v=' + MEAS_JS_V,
    '/static/js/measurement/manual-rows.js?v=' + MEAS_JS_V,
    '/static/js/measurement/image-export.js?v=' + MEAS_JS_V
  ];

  // 동선 스트립: 셸 탭(fragment) 최초 진입에서도 로드돼야 하지만 CHAIN 의 다른 스크립트
  // 심볼에 의존하지 않는 자체 완결 IIFE 다. CHAIN 마지막에 두면 지도와 무관한 7개
  // 스크립트를 전부 받고 실행할 때까지 Kakao SDK 다운로드가 시작조차 못 하므로
  // (직렬화), 순차 체인에서 빼고 병렬로 즉시 kick 한다.
  // 풀페이지(dashboard.html)의 defer 태그와 이중 로드돼도 __FOMS_ROUTE_STRIP_BOUND
  // (전역 배선)·dataset.fomsRouteStripInit(마운트 렌더) 가드로 idempotent.
  var PARALLEL = [
    '/static/js/measurement/foms-route-strip.js?v=' + MEAS_JS_V
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

  // 순서 의존이 없는 스크립트를 CHAIN 과 병렬로 즉시 내려받는다.
  // async=true 여야 loadScript 의 async=false 순서 큐에 끼어들지 않는다
  // (async=false 로 넣으면 CHAIN 과 같은 in-order 큐에 묶여 직렬화가 되살아난다).
  // 셸 프래그먼트 스왑마다 kick() 이 재호출되므로 플래그로 script 주입은 1회만.
  function loadParallelOnce() {
    if (window.__fomsMeasurementParallelLoaded) return;
    window.__fomsMeasurementParallelLoaded = true;
    for (var i = 0; i < PARALLEL.length; i++) {
      var s = document.createElement('script');
      s.src = PARALLEL[i];
      s.async = true;
      s.onerror = (function (src) {
        return function () { console.error('[measurement-entry] Failed to load ' + src); };
      })(PARALLEL[i]);
      document.head.appendChild(s);
    }
  }

  function hasMeasurementRoot() {
    return !!(
      document.querySelector('#main-content .erp-measurement-dashboard') ||
      document.querySelector('.erp-measurement-dashboard')
    );
  }

  function ensureBundle() {
    if (window.__fomsMeasurementBundleLoaded) {
      return Promise.resolve();
    }
    if (window.__fomsMeasurementBundlePromise) {
      return window.__fomsMeasurementBundlePromise;
    }
    if (!hasMeasurementRoot()) {
      return Promise.resolve();
    }
    // 지도(동선 스트립)는 CHAIN 완주를 기다리지 않고 여기서 바로 출발한다 — await 금지.
    loadParallelOnce();
    window.__fomsMeasurementBundlePromise = (async function () {
      for (var i = 0; i < CHAIN.length; i++) {
        await loadScript(CHAIN[i]);
      }
      window.__fomsMeasurementBundleLoaded = true;
      window.__fomsMeasurementBundlePromise = null;
    })().catch(function (err) {
      window.__fomsMeasurementBundlePromise = null;
      console.error('[measurement-entry]', err);
      throw err;
    });
    return window.__fomsMeasurementBundlePromise;
  }

  function kick() {
    ensureBundle();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', kick);
  } else {
    kick();
  }

  if (!window.__fomsMeasurementEntryInstalled) {
    window.__fomsMeasurementEntryInstalled = true;
    document.addEventListener('foms:erp-shell-fragment-swapped', kick);
  }
})();
