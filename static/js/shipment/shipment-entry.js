/**
 * 출고(시공) 대시보드: 외부 번들 순차 로드 (프래그먼트 HTML에는 마크업/데이터만 두고 스크립트 이중 실행 방지).
 * 최초 1회만 로드; 셸 탭 전환으로 HTML만 바뀔 때는 각 모듈의 foms:erp-shell-fragment-swapped 리스너가 재초기화.
 *
 * 이 entry 태그는 fragment(dashboard_scripts.html) 안에 있어 탭 스왑마다 재실행될 수 있으나,
 * (1) 번들 로드는 __fomsShipmentBundleLoaded singleton 으로 1회, (2) 스왑 리스너 등록은
 * __fomsShipmentEntryInstalled 가드로 1회만 하여 listener 누적을 막는다.
 * (실측탭 5.8s 사건과 같은 병·같은 처방: fragment 내 다중 <script src> → entry singleton.)
 */
(function () {
  var SHIP_JS_V = '20260730d';
  var CHAIN = [
    '/static/js/shipment/image-export.js?v=' + SHIP_JS_V,
    '/static/js/shipment/dashboard-columns.js?v=' + SHIP_JS_V
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

  function hasShipmentRoot() {
    return !!(
      document.getElementById('shipment-dashboard-table') ||
      document.querySelector('.shipment-table') ||
      document.getElementById('btn-export-image')
    );
  }

  function ensureBundle() {
    if (window.__fomsShipmentBundleLoaded) {
      return Promise.resolve();
    }
    if (window.__fomsShipmentBundlePromise) {
      return window.__fomsShipmentBundlePromise;
    }
    if (!hasShipmentRoot()) {
      return Promise.resolve();
    }
    window.__fomsShipmentBundlePromise = (async function () {
      for (var i = 0; i < CHAIN.length; i++) {
        await loadScript(CHAIN[i]);
      }
      window.__fomsShipmentBundleLoaded = true;
      window.__fomsShipmentBundlePromise = null;
    })().catch(function (err) {
      window.__fomsShipmentBundlePromise = null;
      console.error('[shipment-entry]', err);
      throw err;
    });
    return window.__fomsShipmentBundlePromise;
  }

  function kick() {
    ensureBundle();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', kick);
  } else {
    kick();
  }

  if (!window.__fomsShipmentEntryInstalled) {
    window.__fomsShipmentEntryInstalled = true;
    document.addEventListener('foms:erp-shell-fragment-swapped', kick);
  }
})();
