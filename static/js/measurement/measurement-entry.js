/**
 * 실측 대시보드: 외부 번들 순차 로드 (프래그먼트 HTML에는 마크업/데이터만 두고 스크립트 이중 실행 방지).
 * 최초 1회만 로드; 셸 탭 전환으로 HTML만 바뀔 때는 각 모듈의 foms:erp-shell-fragment-swapped 리스너가 재초기화.
 *
 * 이 entry 태그는 fragment(dashboard_scripts.html) 안에 있어 탭 스왑마다 재실행될 수 있으나,
 * (1) 번들 로드는 __fomsMeasurementBundleLoaded singleton 으로 1회, (2) 스왑 리스너 등록은
 * __fomsMeasurementEntryInstalled 가드로 1회만 하여 listener 누적을 막는다.
 */
(function () {
  var MEAS_JS_V = '20260703b';
  var CHAIN = [
    '/static/js/runtime/common_utils.js?v=' + MEAS_JS_V,
    '/static/js/measurement/dashboard.js?v=' + MEAS_JS_V,
    '/static/js/measurement/mobile.js?v=' + MEAS_JS_V,
    '/static/js/runtime/column-resizer.js?v=' + MEAS_JS_V,
    '/static/js/measurement/dashboard-columns.js?v=' + MEAS_JS_V,
    '/static/js/measurement/manual-rows.js?v=' + MEAS_JS_V,
    '/static/js/measurement/image-export.js?v=' + MEAS_JS_V
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
