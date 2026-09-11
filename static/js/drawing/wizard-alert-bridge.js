/**
 * 도면 마법사 ↔ 수정 요청 확인창 브리지.
 *
 * 마법사는 `layout_head` 를 상속하지 않는 standalone 문서라 공용 상단바의 벨·배지·Socket.IO
 * 부트스트랩이 통째로 빠져 있었다. 도면팀이 가장 오래 머무는 화면이 알림 사각지대였고,
 * 2026-09-11 실측에서 90일 수정 요청 21건 중 8건이 미독이었다.
 *
 * 여기서는 상단바를 들이지 않고(캔버스 단축키·레이아웃 충돌) **소켓 연결과 확인창 바인딩만**
 * 한다. 등급 판정은 서버 payload 의 `interrupt` 가 하고, 표시·확인 처리는
 * `foms-drawing-alert.js` 가 한다.
 */
(function () {
  'use strict';

  var RETRY_MS = 700;
  var MAX_TRIES = 12;
  var tries = 0;

  function connect() {
    tries += 1;
    if (typeof window.io === 'undefined' || !window.FOMSDrawingAlert) {
      if (tries < MAX_TRIES) {
        window.setTimeout(connect, RETRY_MS);
      } else if (window.FOMS_DEBUG) {
        console.warn('[wizard-alert] Socket.IO 또는 확인창 모듈을 못 찾았다 — 알림 없이 계속한다.');
      }
      return;
    }
    if (window.__wizardAlertSocket) return;

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
      console.warn('[wizard-alert] 소켓 생성 실패:', e);
      return;
    }
    window.__wizardAlertSocket = socket;
    window.FOMSDrawingAlert.bindSocket(socket);
    if (window.FOMS_DEBUG) {
      socket.on('connect', function () { console.log('[wizard-alert] 소켓 연결'); });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', connect);
  } else {
    connect();
  }
})();
