/**
 * P0-01 KPI baseline: Web Vitals + navigation timing → /api/foms/rum (Railway logs).
 */
(function () {
  'use strict';

  var ENDPOINT = '/api/foms/rum';

  /**
   * POST a metric payload; prefers sendBeacon for unload safety.
   *
   * @param {Record<string, unknown>} body
   */
  function sendMetric(body) {
    var json = JSON.stringify(body);
    if (navigator.sendBeacon) {
      navigator.sendBeacon(ENDPOINT, new Blob([json], { type: 'application/json' }));
      return;
    }
    fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: json,
      keepalive: true,
    }).catch(function () { /* ignore */ });
  }

  function basePayload() {
    return {
      path: window.location.pathname,
      viewport: window.innerWidth + 'x' + window.innerHeight,
      mobile_v2: document.body && document.body.classList.contains('erp-mobile-v2-layout'),
    };
  }

  if ('PerformanceObserver' in window) {
    try {
      new PerformanceObserver(function (list) {
        var entries = list.getEntries();
        var last = entries[entries.length - 1];
        if (last) {
          sendMetric(Object.assign(basePayload(), { metric: 'LCP', value: Math.round(last.startTime) }));
        }
      }).observe({ type: 'largest-contentful-paint', buffered: true });
    } catch (e) { /* unsupported */ }

    try {
      new PerformanceObserver(function (list) {
        list.getEntries().forEach(function (entry) {
          if (entry.interactionId) {
            sendMetric(Object.assign(basePayload(), {
              metric: 'INP',
              value: Math.round(entry.duration),
            }));
          }
        });
      }).observe({ type: 'event', buffered: true, durationThreshold: 40 });
    } catch (e) { /* unsupported */ }
  }

  // Navigation Timing: load 핸들러 실행 중 loadEventEnd 는 아직 0 인 브라우저가 있다.
  // (스펙상 load 이벤트 처리가 끝나야 loadEventEnd 가 채워짐) → setTimeout(0) 후 재측정.
  function sendLoadMetric() {
    var nav = performance.getEntriesByType('navigation')[0];
    if (!nav) { return; }
    var value = Math.round(nav.loadEventEnd || nav.duration || 0);
    if (value <= 0) { return; }
    sendMetric(Object.assign(basePayload(), { metric: 'LOAD', value: value }));
  }
  if (document.readyState === 'complete') {
    setTimeout(sendLoadMetric, 0);
  } else {
    window.addEventListener('load', function () {
      setTimeout(sendLoadMetric, 0);
    });
  }

  // ERP 셸 탭 프래그먼트 스왑 소요(사용자 누름→콘텐츠 교체 완료)를 10% 샘플로 전송.
  // click→swapped 델타로 측정하므로 라우팅 로직 중복 없이 rum-baseline 안에서 완결된다.
  if (!window.__FOMS_RUM_SWAP_BOUND) {
    window.__FOMS_RUM_SWAP_BOUND = true;
    var lastPressAt = 0;
    document.addEventListener('pointerdown', function () {
      lastPressAt = (performance && performance.now) ? performance.now() : Date.now();
    }, { passive: true, capture: true });
    // 뒤로가기 스왑은 press→swap 페어가 아님 — 스왑과 무관한 이전 pointerdown 이
    // popstate 스왑과 짝지어지는 측정 오염을 차단(1:1 리뷰 반영).
    window.addEventListener('popstate', function () {
      lastPressAt = 0;
    });
    document.addEventListener('foms:erp-shell-fragment-swapped', function () {
      if (!lastPressAt) { return; }
      var now = (performance && performance.now) ? performance.now() : Date.now();
      var delta = now - lastPressAt;
      lastPressAt = 0; // 1스왑=1측정, 이후 stale 재사용 방지
      // 유효 범위 밖(음수/과대=뒤로가기·오래된 누름)은 버린다.
      if (delta <= 0 || delta > 20000) { return; }
      if (Math.random() >= 0.1) { return; } // 10% 샘플링
      sendMetric(Object.assign(basePayload(), {
        metric: 'SWAP',
        value: Math.round(delta),
      }));
    });
  }
})();
