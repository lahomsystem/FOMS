/**
 * 출고(시공) 대시보드: 외부 번들을 한꺼번에 받고 순서대로 실행 (프래그먼트 HTML에는 마크업/데이터만 두고 스크립트 이중 실행 방지).
 * 최초 1회만 로드; 셸 탭 전환으로 HTML만 바뀔 때는 각 모듈의 foms:erp-shell-fragment-swapped 리스너가 재초기화.
 *
 * 이 entry 태그는 fragment(dashboard_scripts.html) 안에 있어 탭 스왑마다 재실행될 수 있으나,
 * (1) 번들 로드는 __fomsShipmentBundleLoaded singleton 으로 1회, (2) 스왑 리스너 등록은
 * __fomsShipmentEntryInstalled 가드로 1회만 하여 listener 누적을 막는다.
 * (실측탭 5.8s 사건과 같은 병·같은 처방: fragment 내 다중 <script src> → entry singleton.)
 * 태블릿 도메인 시트(tablet-domain-sheets.js)도 이 CHAIN 이 싣는다 — 파샬에 두면 <script src> 가 2개라
 * 스왑마다 다시 실행되고 perf_scan fragment-multi-script 가 파샬 수정(엔트리 핀 범프)을 막는다.
 */
(function () {
  var SHIP_JS_V = '20260730e';
  var CHAIN = [
    '/static/js/shipment/image-export.js?v=' + SHIP_JS_V,
    '/static/js/shipment/dashboard-columns.js?v=' + SHIP_JS_V,
    // 생산 태블릿 칸반(tablet_kanban_body.html)과 같은 파일·같은 핀 — 캐시 한 벌을 나눠 쓰고,
    // 두 화면에서 모두 실려도 모듈 싱글턴(__FOMS_DOMAIN_SHEETS_BOUND)이 두 번째 실행을 막는다.
    // 핀을 올릴 때는 그 파샬과 함께 올린다.
    '/static/js/foms/tablet-domain-sheets.js?v=20260921a'
  ];

  // 파일마다 로드 Promise 를 기억한다. 실패 뒤 다시 부를 때 이미 실행됐거나 받는 중인
  // 파일은 또 넣지 않는다 — 같은 파일이 두 번 실행되면 전역 리스너가 겹친다.
  var loads = window.__fomsShipmentChainLoads || (window.__fomsShipmentChainLoads = {});

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
    // 하나씩 기다리며 넣으면 파일 수만큼 왕복이 줄 선다.
    // 한꺼번에 넣고 전부 끝나기를 기다린다. 실행 순서는 async=false 가 지킨다.
    window.__fomsShipmentBundlePromise = Promise.all(CHAIN.map(loadScript)).then(function () {
      window.__fomsShipmentBundleLoaded = true;
      window.__fomsShipmentBundlePromise = null;
    }).catch(function (err) {
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
