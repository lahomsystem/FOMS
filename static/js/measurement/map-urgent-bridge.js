/**
 * 실측 지도 ↔ 긴급 알림 빨간 창 브리지.
 *
 * 실측 지도(`templates/measurement/map_view.html`)는 `layout_head` 를 쓰지 않는 standalone 문서라
 * 공용 상단바의 Socket.IO 부트스트랩이 없었고, 긴급 멘션·공지가 이 화면에서는 뜨지 않았다
 * (SPEC 2026-10-02 urgent-alert-everywhere).
 *
 * 마법사 브리지(`static/js/drawing/wizard-alert-bridge.js`)와 같은 형태로 **소켓 연결과
 * 빨간 창 바인딩만** 한다. 표시·확인·재조회는 `foms-urgent-alert.js` 가 한다.
 */
(function () {
  'use strict';

  var RETRY_MS = 700;
  var MAX_TRIES = 12;
  var tries = 0;

  function connect() {
    tries += 1;
    if (typeof window.io === 'undefined' || !window.FOMSUrgentAlert) {
      if (tries < MAX_TRIES) {
        window.setTimeout(connect, RETRY_MS);
      } else if (window.FOMS_DEBUG) {
        console.warn('[map-urgent] Socket.IO 또는 빨간 창 모듈을 못 찾았다 — 알림 없이 계속한다.');
      }
      return;
    }
    if (window.__mapUrgentSocket) return;

    var socket;
    try {
      socket = window.io({
        transports: ['websocket', 'polling'],
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        timeout: 30000
      });
    } catch (e) {
      console.warn('[map-urgent] 소켓 생성 실패:', e);
      return;
    }
    window.__mapUrgentSocket = socket;
    window.FOMSUrgentAlert.bindSocket(socket);
    if (window.FOMS_DEBUG) {
      socket.on('connect', function () { console.log('[map-urgent] 소켓 연결'); });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', connect);
  } else {
    connect();
  }
})();
