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

    // INP 는 화면 하나에서 가장 느린 상호작용 1건이다. 이벤트 항목마다 보내면 글자 입력 한
    // 번에 keydown·keyup·input 이 각각 나가 운영 web 요청의 40% 를 차지했고 서버 한도(429)에
    // 걸렸다(2026-10-01 실측). 최댓값만 들고 있다가 화면을 떠날 때·탭 전환 때 한 번 보낸다.
    var worstInp = null;
    // 기기 한 대가 하루에 보내는 INP 는 INP_DAILY_CAP 건까지다. 느린 태블릿 1대가 하루 34~56건을
    // 보내 일별 p95 를 끌어올려 rum-daily 가 red 가 됐다(2026-10-07). 하루 약 1,000건 중 2% 이하로 묶는다.
    // storage 를 못 쓰면(사생활 보호 모드 등) 지금처럼 보낸다.
    var INP_DAILY_CAP = 20;
    var INP_DAILY_KEY = 'foms_rum_inp_daily';
    function takeInpDailySlot() {
      try {
        var d = new Date();
        var today = d.getFullYear() + '-' + (d.getMonth() + 1) + '-' + d.getDate();
        var saved = JSON.parse(window.localStorage.getItem(INP_DAILY_KEY) || 'null');
        var count = saved && saved.date === today ? saved.count : 0;
        if (count >= INP_DAILY_CAP) { return false; }
        window.localStorage.setItem(INP_DAILY_KEY, JSON.stringify({ date: today, count: count + 1 }));
      } catch (e) { /* storage 불가 — 보낸다 */ }
      return true;
    }
    function flushInp() {
      if (!worstInp) { return; }
      var payload = worstInp;
      worstInp = null;
      if (!takeInpDailySlot()) { return; }
      sendMetric(payload);
    }
    try {
      new PerformanceObserver(function (list) {
        list.getEntries().forEach(function (entry) {
          if (!entry.interactionId) { return; }
          var value = Math.round(entry.duration);
          if (worstInp && worstInp.value >= value) { return; }
          worstInp = Object.assign(basePayload(), { metric: 'INP', value: value });
        });
      }).observe({ type: 'event', buffered: true, durationThreshold: 40 });
      document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') { flushInp(); }
      });
      window.addEventListener('pagehide', flushInp);
      // ERP 셸은 새로고침 없이 화면을 갈아 끼운다 — 앞 화면 몫을 그 화면 경로로 마감한다.
      document.addEventListener('foms:erp-shell-fragment-swapped', flushInp);
    } catch (e) { /* unsupported */ }
  }

  // Navigation Timing: load 핸들러 실행 중 loadEventEnd 는 아직 0 인 브라우저가 있다.
  // (스펙상 load 이벤트 처리가 끝나야 loadEventEnd 가 채워짐) → setTimeout(0) 후 재측정.
  // 느린 LOAD(3초 이상)에만 "무엇을 기다렸나" 분해를 싣는다 — 단계별 시간 + 오래 걸린 파일 3개.
  // 사진 주소·서명·주문 번호를 남기지 않도록 우리 /static/ 만 경로, 나머지는 확장자만 보낸다.
  // (docs/specs/2026-10-21-rum-slow-load-breakdown_SPEC.md)
  var SLOW_LOAD_MS = 3000;
  function clampMs(x) {
    var v = Math.round(x || 0);
    return v < 0 ? 0 : (v > 120000 ? 120000 : v);
  }
  function navBreakdown(nav) {
    return {
      dns: clampMs(nav.domainLookupEnd - nav.domainLookupStart),
      conn: clampMs(nav.connectEnd - nav.connectStart),
      ttfb: clampMs(nav.responseStart - nav.requestStart),
      resp: clampMs(nav.responseEnd - nav.responseStart),
      dcl: clampMs(nav.domContentLoadedEventEnd),
      redir: clampMs(nav.redirectEnd - nav.redirectStart),
    };
  }
  function slowResources() {
    var entries = performance.getEntriesByType('resource').slice();
    entries.sort(function (a, b) { return b.duration - a.duration; });
    return entries.slice(0, 3).map(function (e) {
      var u;
      try { u = new URL(e.name); } catch (err) { u = null; }
      var host = u ? u.hostname : 'unknown';
      var path = '.none';
      if (u && u.origin === window.location.origin && u.pathname.indexOf('/static/') === 0 && u.pathname.length <= 200) {
        path = u.pathname;
      } else if (u) {
        var ext = u.pathname.match(/\.[A-Za-z0-9]{1,8}$/);
        if (ext) { path = ext[0]; }
      }
      var kind = String(e.initiatorType || '').toLowerCase().replace(/[^a-z]/g, '').slice(0, 8) || 'other';
      return {
        h: /^[A-Za-z0-9.-]+$/.test(host) ? host : 'unknown',
        p: path,
        d: clampMs(e.duration),
        s: clampMs(e.startTime),
        c: (e.transferSize === 0 && e.decodedBodySize > 0) ? 1 : 0,
        k: kind,
      };
    });
  }

  function sendLoadMetric() {
    var nav = performance.getEntriesByType('navigation')[0];
    if (!nav) { return; }
    var value = Math.round(nav.loadEventEnd || nav.duration || 0);
    if (value <= 0) { return; }
    var payload = Object.assign(basePayload(), { metric: 'LOAD', value: value });
    if (value >= SLOW_LOAD_MS) {
      try {
        payload.nav = navBreakdown(nav);
        payload.slow = slowResources();
      } catch (e) { /* 분해 실패 — 숫자만 보낸다 */ }
    }
    sendMetric(payload);
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
