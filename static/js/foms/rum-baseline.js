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

  window.addEventListener('load', function () {
    var nav = performance.getEntriesByType('navigation')[0];
    if (nav && nav.loadEventEnd) {
      sendMetric(Object.assign(basePayload(), {
        metric: 'LOAD',
        value: Math.round(nav.loadEventEnd),
      }));
    }
  });
})();
