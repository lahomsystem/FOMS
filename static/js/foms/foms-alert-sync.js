/**
 * 확인창 보강 — 탭 간 동기 + 끊긴 동안 온 알림 재표시.
 *
 * 왜: 확인창(foms-drawing-alert.js)은 socket 으로 받은 순간에만 뜬다. 그래서
 *   ① 같은 사람이 탭을 여러 개 열면 한 탭에서 확인해도 다른 탭에 창이 남고,
 *   ② 소켓이 끊긴 동안(화면 꺼짐·이동 중) 온 알림은 영영 뜨지 않았다.
 * ①은 BroadcastChannel('foms-alerts') 로 확인 사실을 다른 탭에 알려 닫는다(ack 는 한 번만).
 * ②는 재연결·화면 복귀 때 "내 미확인 확인창 알림"을 서버에서 다시 받아 띄운다.
 *
 * 사용: window.FOMSAlertSync.resync(reason) — layout_head 소켓 onConnect 가 부른다.
 * 재조회 대상(영업·MEASURE 표기 계정)인지는 서버가 script 태그 data-alert-sync-target 으로 준다.
 * 'socket-connect' 는 30초 제한을 받지 않는다(끊긴 사이 온 알림을 곧바로 다시 띄운다).
 */
(function () {
  'use strict';

  if (window.FOMSAlertSync) return;

  var ENDPOINT = '/erp/api/notifications/pending-interrupts';
  var CHANNEL_NAME = 'foms-alerts';
  var STORAGE_KEY = 'foms.alertSync.lastResyncAt';
  var MIN_INTERVAL_MS = 30000;
  var memoryLastAt = 0;
  var inFlight = false;
  var SCRIPT_EL = document.currentScript;
  var RESYNC_TARGET = !!(SCRIPT_EL && SCRIPT_EL.getAttribute('data-alert-sync-target') === '1');

  function alertModule() {
    var mod = window.FOMSDrawingAlert;
    return mod && typeof mod.handle === 'function' ? mod : null;
  }

  // ── 탭 간 동기 ─────────────────────────────────────────────
  var channel = null;
  try {
    if (typeof window.BroadcastChannel === 'function') {
      channel = new BroadcastChannel('foms-alerts');
    }
  } catch (e) {
    channel = null; // 미지원·차단 환경 — 동기만 빠진다.
  }

  if (channel) {
    channel.onmessage = function (event) {
      var msg = event && event.data;
      if (!msg || msg.type !== 'ack' || msg.id == null || msg.id === '') return;
      var mod = alertModule();
      if (mod && typeof mod.dismiss === 'function') mod.dismiss(String(msg.id));
    };
    document.addEventListener('foms:alert-ack', function (event) {
      var id = event && event.detail && event.detail.id;
      if (id == null || id === '') return;
      try {
        channel.postMessage({ type: 'ack', id: String(id) });
      } catch (e) {
        console.warn('[alert-sync] ' + CHANNEL_NAME + ' 전송 실패:', e);
      }
    });
  }

  // ── 미확인 알림 재조회 ──────────────────────────────────────
  function readLastAt() {
    try {
      var raw = window.sessionStorage.getItem(STORAGE_KEY);
      var value = raw ? parseInt(raw, 10) : 0;
      return isNaN(value) ? memoryLastAt : Math.max(value, memoryLastAt);
    } catch (e) {
      return memoryLastAt;
    }
  }

  function writeLastAt(value) {
    memoryLastAt = value;
    try {
      window.sessionStorage.setItem(STORAGE_KEY, String(value));
    } catch (e) { /* 개인 창 등 — 메모리 값만 쓴다. */ }
  }

  async function resync(reason) {
    if (!RESYNC_TARGET || inFlight || !alertModule()) return false;
    var now = Date.now();
    if (reason !== 'socket-connect' && now - readLastAt() < MIN_INTERVAL_MS) return false;
    writeLastAt(now);
    inFlight = true;
    try {
      var response = await fetch(ENDPOINT, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' }
      });
      var data = await response.json();
      if (!data || data.success !== true) {
        console.warn('[alert-sync] 재조회 실패(' + (reason || '') + '):', data && data.error);
        return false;
      }
      var items = (data.data && data.data.items) || [];
      var mod = alertModule();
      items.forEach(function (item) {
        try {
          if (mod) mod.handle(item);
        } catch (e) {
          console.warn('[alert-sync] 확인창 표시 오류:', e);
        }
      });
      return true;
    } catch (err) {
      console.warn('[alert-sync] 재조회 오류(' + (reason || '') + '):', err);
      return false;
    } finally {
      inFlight = false;
    }
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') resync('visible');
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { resync('page-load'); }, { once: true });
  } else {
    resync('page-load');
  }

  window.FOMSAlertSync = { resync: resync };
})();
