/**
 * 실측 대시보드: 외부 번들을 한꺼번에 받고 순서대로 실행 (프래그먼트 HTML에는 마크업/데이터만 두고 스크립트 이중 실행 방지).
 * 최초 1회만 로드; 셸 탭 전환으로 HTML만 바뀔 때는 각 모듈의 foms:erp-shell-fragment-swapped 리스너가 재초기화.
 *
 * 이 entry 태그는 fragment(dashboard_scripts.html) 안에 있어 탭 스왑마다 재실행될 수 있으나,
 * (1) 번들 로드는 __fomsMeasurementBundleLoaded singleton 으로 1회, (2) 스왑 리스너 등록은
 * __fomsMeasurementEntryInstalled 가드로 1회만 하여 listener 누적을 막는다.
 */
(function () {
  var MEAS_JS_V = '20261008s';
  var CHAIN = [
    '/static/js/runtime/common_utils.js?v=' + MEAS_JS_V,
    '/static/js/measurement/dashboard.js?v=' + MEAS_JS_V,
    '/static/js/measurement/mobile.js?v=' + MEAS_JS_V,
    '/static/js/runtime/column-resizer.js?v=' + MEAS_JS_V,
    '/static/js/measurement/dashboard-columns.js?v=' + MEAS_JS_V,
    '/static/js/measurement/manual-rows.js?v=' + MEAS_JS_V,
    '/static/js/measurement/image-save-sheet.js?v=' + MEAS_JS_V,
    '/static/js/measurement/image-export.js?v=' + MEAS_JS_V,
    '/static/js/measurement/mobile-glance.js?v=' + MEAS_JS_V,
    '/static/js/measurement/mobile-glance-tabs.js?v=' + MEAS_JS_V,
    '/static/js/measurement/mobile-glance-sheet-parts.js?v=' + MEAS_JS_V,
    '/static/js/measurement/mobile-glance-sheet.js?v=' + MEAS_JS_V
  ];

  // 파일마다 로드 Promise 를 기억한다. 실패 뒤 다시 부를 때 이미 실행됐거나 받는 중인
  // 파일은 또 넣지 않는다 — 같은 파일이 두 번 실행되면 전역 리스너가 겹친다.
  var loads = window.__fomsMeasurementChainLoads || (window.__fomsMeasurementChainLoads = {});

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
    // 하나씩 기다리며 넣으면 파일 수만큼 왕복이 줄 선다(스테이징 콜드 12개 약 1.3초).
    // 한꺼번에 넣고 전부 끝나기를 기다린다. 실행 순서는 async=false 가 지킨다.
    window.__fomsMeasurementBundlePromise = Promise.all(CHAIN.map(loadScript)).then(function () {
      window.__fomsMeasurementBundleLoaded = true;
      window.__fomsMeasurementBundlePromise = null;
    }).catch(function (err) {
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
