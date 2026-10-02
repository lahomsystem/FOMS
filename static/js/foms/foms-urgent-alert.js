/**
 * 긴급(P0) 전체화면 빨간 창 공용 모듈 — SPEC docs/specs/2026-10-02-urgent-alert-everywhere_SPEC.md.
 * 공개 계약(이름 고정 — standalone 브리지가 부른다): handle(data) · show(data) · bindSocket(socket)
 *   · resync(reason) · openFromPush(notificationId). 대기열로 한 건씩, notification_id 로 중복 제거,
 *   BroadcastChannel('foms-urgent') 로 탭 간 ack 동기. "확인" 버튼 하나로만 닫힌다(배경·Esc 무시).
 */
(function () {
  'use strict';

  if (window.FOMSUrgentAlert) return;

  var ENDPOINT = '/erp/api/notifications/pending-urgent';
  var CHANNEL_NAME = 'foms-urgent';
  var MIN_INTERVAL_MS = 30000;
  var UNTHROTTLED = { 'socket-connect': 1, 'sw-click': 1 };
  var KEY_EVENTS = ['keydown', 'keypress', 'keyup'];

  var queue = [];
  var acked = {};
  var lastResyncAt = 0;
  var inFlight = false;
  var overlay = null;
  var refs = null;
  var prevFocus = null;
  var busy = false;
  var shownItem = null;

  function norm(id) { return (id == null || id === '') ? '' : String(id); }
  function idOf(item) { return norm(item && item.notification_id); }

  function indexOfId(id) {
    for (var i = 0; id && i < queue.length; i += 1) if (idOf(queue[i]) === id) return i;
    return -1;
  }

  function beep() {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      var ctx = new Ctx(), osc = ctx.createOscillator(), gain = ctx.createGain(), now = ctx.currentTime;
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = 'square';
      osc.frequency.setValueAtTime(880, now);
      osc.frequency.exponentialRampToValueAtTime(440, now + 0.1);
      gain.gain.setValueAtTime(0.1, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
      osc.start();
      osc.stop(now + 0.3);
    } catch (e) { console.warn('[urgent-alert] 소리 재생 실패:', e); }
  }

  // ── 키 가둠: 오버레이 뒤 화면 단축키(마법사 캔버스 등)가 먹지 않게 ──────────
  function onKey(event) {
    if (!overlay) return;
    var btn = refs && refs.btn;
    var onBtn = btn && event.target === btn;
    var activates = onBtn && (event.key === 'Enter' || event.key === ' ' || event.key === 'Spacebar');
    event.stopImmediatePropagation();
    if (activates) return; // 버튼 기본 동작(클릭)은 살린다.
    event.preventDefault();
    if (event.type === 'keydown' && btn && !btn.disabled) btn.focus();
  }

  function onFocusIn(event) {
    if (overlay && refs && !overlay.contains(event.target)) refs.btn.focus();
  }
  function toggleKeys(on) {
    var m = on ? 'addEventListener' : 'removeEventListener';
    KEY_EVENTS.forEach(function (t) { window[m](t, onKey, true); });
    document[m]('focusin', onFocusIn, true);
  }

  function el(tag, cls, parent, id) {
    var node = document.createElement(tag);
    node.className = cls;
    if (id) node.id = id;
    if (parent) parent.appendChild(node);
    return node;
  }

  function buildOverlay() {
    var root = el('div', 'foms-urgent-alert', null, 'foms-urgent-alert');
    [['role', 'alertdialog'], ['aria-modal', 'true'], ['aria-labelledby', 'foms-urgent-alert-title'],
      ['aria-describedby', 'foms-urgent-alert-message']].forEach(function (a) { root.setAttribute(a[0], a[1]); });
    var box = el('div', 'foms-urgent-alert__box', root);
    var icon = el('div', 'foms-urgent-alert__icon', box);
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = '🔔';
    var count = el('div', 'foms-urgent-alert__count', box);
    var title = el('h1', 'foms-urgent-alert__title', box, 'foms-urgent-alert-title');
    var message = el('p', 'foms-urgent-alert__message', box, 'foms-urgent-alert-message');
    var sender = el('p', 'foms-urgent-alert__sender', box);
    var error = el('p', 'foms-urgent-alert__error', box);
    error.setAttribute('role', 'status');
    var btn = el('button', 'foms-urgent-alert__btn', box);
    btn.type = 'button';
    btn.textContent = '확인';
    btn.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopPropagation();
      confirmCurrent();
    });
    // 배경 클릭은 아무것도 하지 않는다(닫기 금지) — 뒤 화면으로 새지 않게만 막는다.
    root.addEventListener('click', function (event) { event.stopPropagation(); });
    refs = { count: count, title: title, message: message, sender: sender, error: error, btn: btn };
    return root;
  }

  function render() {
    if (!queue.length) {
      if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
      if (overlay) toggleKeys(false);
      overlay = null;
      refs = null;
      shownItem = null;
      if (prevFocus && typeof prevFocus.focus === 'function') {
        try { prevFocus.focus(); } catch (e) { /* 사라진 요소 — 무시 */ }
      }
      prevFocus = null;
      return;
    }
    if (!document.body) return;
    if (!overlay) {
      prevFocus = document.activeElement;
      overlay = buildOverlay();
      document.body.appendChild(overlay);
      toggleKeys(true);
    }
    var item = queue[0];
    refs.count.textContent = queue.length > 1 ? ('긴급 ' + queue.length + '건 중 1') : '';
    refs.count.hidden = queue.length <= 1;
    if (shownItem === item) return; // 대기 건수만 바뀜 — 진행 중인 확인 처리는 건드리지 않는다.
    shownItem = item;
    refs.title.textContent = item.title ? String(item.title) : '긴급 알림';
    refs.message.textContent = item.message ? String(item.message) : '상세 내용은 알림 패널을 확인하세요.';
    refs.sender.textContent = item.created_by_name ? ('보낸 사람: ' + String(item.created_by_name)) : '';
    refs.sender.hidden = !item.created_by_name;
    refs.error.textContent = '';
    refs.error.hidden = true;
    refs.btn.disabled = false;
    busy = false;
    refs.btn.focus();
  }

  function removeId(id) {
    var idx = indexOfId(id);
    if (idx >= 0) { queue.splice(idx, 1); render(); }
  }

  function showError(text) {
    busy = false;
    if (!refs) return;
    refs.error.textContent = text;
    refs.error.hidden = false;
    refs.btn.disabled = false;
    refs.btn.focus();
  }

  function postAck(id) {
    var url = '/erp/api/notifications/' + encodeURIComponent(id) + '/ack';
    var opts = { method: 'POST', headers: { 'Accept': 'application/json' } };
    if (window.FOMSNotificationWrite && typeof window.FOMSNotificationWrite.fetch === 'function') {
      return window.FOMSNotificationWrite.fetch(url, opts);
    }
    var headers = { 'Accept': 'application/json', 'X-FOMS-Notification-Write': '1' };
    if (typeof window.fomsCsrfToken === 'function') headers['X-CSRF-Token'] = window.fomsCsrfToken();
    return window.fetch(url, { method: 'POST', headers: headers, credentials: 'same-origin' });
  }

  function confirmCurrent() {
    if (busy || !queue.length) return;
    var id = idOf(queue[0]);
    if (!id) { queue.shift(); render(); return; } // 에스컬레이션 경고 — 기록할 id 가 없으니 닫기만.
    busy = true;
    refs.btn.disabled = true;
    postAck(id)
      // 404 = 내 알림이 아니거나 지워짐 — 기록할 대상이 없으니 닫는다(영영 못 닫는 창 방지).
      .then(function (res) { return res.status === 404 ? { success: true } : res.json(); })
      .then(function (data) {
        if (!data || !data.success) {
          showError(String((data && (data.error || data.message)) || '확인 처리에 실패했습니다. 다시 눌러 주세요.'));
          return;
        }
        acked[id] = true;
        removeId(id);
        if (window.FOMSNotificationBadge && typeof window.FOMSNotificationBadge.refresh === 'function') {
          window.FOMSNotificationBadge.refresh({ force: true });
        }
        broadcastAck(id);
      })
      .catch(function (e) {
        console.warn('[urgent-alert] 확인 처리 오류:', e);
        showError('확인 처리 중 오류가 났습니다. 인터넷 연결을 확인하고 다시 눌러 주세요.');
      });
  }

  // ── 탭 간 동기 ─────────────────────────────────────────────
  var channel = null;
  try {
    if (typeof window.BroadcastChannel === 'function') channel = new BroadcastChannel(CHANNEL_NAME);
  } catch (e) { channel = null; } // 미지원·차단 환경 — 동기만 빠진다.
  if (channel) {
    channel.onmessage = function (event) {
      var msg = event && event.data;
      var id = msg && msg.type === 'ack' ? idOf(msg) : '';
      if (!id) return;
      acked[id] = true;
      removeId(id);
    };
  }

  function broadcastAck(id) {
    try {
      if (channel) channel.postMessage({ type: 'ack', notification_id: id });
    } catch (e) { console.warn('[urgent-alert] 탭 간 전송 실패:', e); }
  }

  // ── 공개 API ───────────────────────────────────────────────
  function show(data) {
    if (!data || typeof data !== 'object') return false;
    var id = idOf(data);
    if (id && (acked[id] || indexOfId(id) >= 0)) return false;
    queue.push(data);
    beep();
    if (document.body) render(); // 첫 건이면 띄우고, 아니면 대기 건수만 갱신
    else document.addEventListener('DOMContentLoaded', render, { once: true });
    return true;
  }

  function handle(data) {
    if (!data || data.urgent !== true) return false;
    show(data);
    return true;
  }

  function resync(reason) {
    var now = Date.now();
    if (inFlight || (!UNTHROTTLED[reason] && now - lastResyncAt < MIN_INTERVAL_MS)) return;
    lastResyncAt = now;
    inFlight = true;
    window.fetch(ENDPOINT, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data || !data.success || !data.data || !Array.isArray(data.data.items)) return;
        data.data.items.forEach(function (item) {
          if (item && typeof item === 'object') show(Object.assign({ urgent: true }, item));
        });
      })
      .catch(function (e) {
        if (window.FOMS_DEBUG) console.warn('[urgent-alert] 재조회 실패(' + reason + '):', e);
      })
      .then(function () { inFlight = false; });
  }

  function openFromPush(notificationId) {
    var idx = indexOfId(norm(notificationId));
    if (idx >= 0) {
      if (idx > 0) queue.unshift(queue.splice(idx, 1)[0]);
      render();
      return;
    }
    resync('sw-click');
  }

  function bindSocket(socket) {
    if (!socket || typeof socket.on !== 'function' || socket.__fomsUrgentBound) return;
    socket.__fomsUrgentBound = true;
    socket.on('erp_notification', handle);
    socket.on('connect', function () { resync('socket-connect'); });
  }

  window.FOMSUrgentAlert = { show: show, handle: handle, bindSocket: bindSocket, resync: resync, openFromPush: openFromPush };
  // 호환 별칭: 예전 인라인 함수 이름으로 부르는 곳이 남아 있어도 같은 창을 쓴다.
  window.triggerUrgentBriefingAlert = function (d) {
    return window.FOMSUrgentAlert.show(Object.assign({ urgent: true }, d));
  };

  // PC 팝업(OS 웹푸시) 클릭 → sw.js 가 창을 다시 읽지 않고 이 메시지를 보낸다.
  try {
    if (navigator.serviceWorker && typeof navigator.serviceWorker.addEventListener === 'function') {
      navigator.serviceWorker.addEventListener('message', function (event) {
        var msg = event && event.data;
        if (msg && msg.type === 'foms-urgent-open') openFromPush(msg.notification_id);
      });
    }
  } catch (e) { console.warn('[urgent-alert] 서비스 워커 메시지 연결 실패:', e); }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') resync('visible');
  });

  // 새로 연 창: 닫혀 있던 동안 온 미확인 긴급을 바로 띄운다.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { resync('load'); }, { once: true });
  } else resync('load');
})();
