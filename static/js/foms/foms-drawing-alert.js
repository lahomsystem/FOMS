/**
 * 확인창 (ACTION-REQUIRED 등급) — 도면 수정 요청 + 당일 실측 긴급 추가(alert_kind 'measure_same_day').
 *
 * 왜: 수정 요청이 종 배지로만 와서 2026-09-11 실측 90일 21건 중 8건(38%)이 미독이었다. 긴급
 * 호출(P0) 전체화면 빨강은 과하다 — 그 사이 등급으로 **확인을 눌러야 닫히는 중앙 확인창**.
 * 등급 판정은 서버 몫: `interrupt: true` → 확인창(ack 기록), `notice: true` → 쪽지(닫으면 읽음).
 * 당일 실측이 끼면 대기열로 받는다(덮어쓰면 앞 알림이 확인되지 않는다). 도면 동작은 그대로.
 * 사용: window.FOMSDrawingAlert.show / notice / handle / bindSocket / dismiss / markShown
 * 이벤트: document 'foms:alert-shown'·'foms:alert-ack' (detail.id) — 탭 간 동기는 foms-alert-sync.js.
 */
(function () {
  'use strict';

  if (window.FOMSDrawingAlert) return;

  var ROOT_ID = 'foms-drawing-alert';
  var MEASURE_KIND = 'measure_same_day';
  var shown = Object.create(null);
  var queue = [];
  var currentKey = null;
  var audioCtx = null;

  function esc(value) {
    return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function emit(name, id) {
    try { document.dispatchEvent(new CustomEvent(name, { detail: { id: id } })); } catch (e) { }
  }

  // 소리 준비: 브라우저는 사람 입력 전에는 소리를 막는다 → 입력 때 하나 만들어 재사용.
  // 'running' 이 될 때까지 입력마다 다시 시도한다(아이폰은 pointerdown 으로는 안 풀린다).
  var PRIME_EVENTS = ['pointerup', 'touchend', 'click', 'keydown'];
  function unbindPrime() { PRIME_EVENTS.forEach(function (n) { document.removeEventListener(n, primeAudio, true); }); }
  function primeAudio() {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) { unbindPrime(); return; }
      if (!audioCtx) audioCtx = new Ctx();
      if (audioCtx.state === 'running') { unbindPrime(); return; }
      if (typeof audioCtx.resume === 'function') {
        audioCtx.resume().then(function () { if (audioCtx.state === 'running') unbindPrime(); })
          .catch(function () { /* 다음 입력 때 다시 시도 */ });
      }
    } catch (e) { /* 소리는 부가 신호다. */ }
  }
  PRIME_EVENTS.forEach(function (name) { document.addEventListener(name, primeAudio, true); });

  function beep(kind) {
    // 당일 실측은 보이는 탭만 울린다(탭이 여러 개면 한 번만). 도면은 기존대로.
    if (kind === MEASURE_KIND && document.visibilityState !== 'visible') return;
    try {
      if (!audioCtx) primeAudio();
      var ctx = audioCtx;
      if (!ctx) return;
      var tone = function () {
        var osc = ctx.createOscillator(), gain = ctx.createGain();
        osc.connect(gain); gain.connect(ctx.destination);
        osc.type = 'sine';
        osc.frequency.setValueAtTime(660, ctx.currentTime);
        gain.gain.setValueAtTime(0.07, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.28);
        osc.start(); osc.stop(ctx.currentTime + 0.3);
      };
      if (ctx.state === 'suspended') ctx.resume().then(tone).catch(function () { });
      else if (ctx.state === 'running') tone();
    } catch (e) { /* 소리는 부가 신호다 — 실패해도 창은 뜬다. */ }
  }

  function deepLink(data) {
    var orderId = data && (data.order_id || data.orderId);
    return orderId ? '/erp/drawing-workbench/' + encodeURIComponent(orderId) + '?tab=requests' : '';
  }

  // 같은 출처 ERP 경로만 허용한다(javascript:·외부 주소 차단).
  function safeOrderUrl(value) { return String(value || '').indexOf('/erp/') === 0 ? String(value) : ''; }

  function shortTime(value) { var t = String(value || '').replace('T', ' '); return /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(t) ? t.slice(0, 16) : t; }

  function ensureRoot() {
    var root = document.getElementById(ROOT_ID);
    if (root) return root;
    root = document.createElement('div');
    root.id = ROOT_ID;
    root.className = 'foms-drawing-alert';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-labelledby', ROOT_ID + '-title');
    root.hidden = true;
    root.innerHTML = [
      '<div class="foms-drawing-alert__card">',
      '  <p class="foms-drawing-alert__kicker" data-role="kicker">도면 수정 요청</p>',
      '  <h2 class="foms-drawing-alert__title" id="' + ROOT_ID + '-title" data-role="title"></h2>',
      '  <p class="foms-drawing-alert__body" data-role="message"></p>',
      '  <p class="foms-drawing-alert__meta" data-role="meta"></p>',
      '  <div class="foms-drawing-alert__acts">',
      '    <button type="button" class="foms-drawing-alert__btn foms-drawing-alert__btn--primary" data-role="ack">확인했습니다</button>',
      '    <a class="foms-drawing-alert__btn" data-role="open" href="#">작업실에서 열기</a>',
      '  </div>',
      '</div>'
    ].join('');
    document.body.appendChild(root);

    root.querySelector('[data-role="ack"]').addEventListener('click', function () {
      acknowledge(root, { close: true });
    });
    root.querySelector('[data-role="open"]').addEventListener('click', function () {
      // 이동 전에 확인 처리한다 — 링크를 눌렀다는 건 본 것이다.
      acknowledge(root, { close: false });
    });
    return root;
  }

  function hideRoot(root) {
    root.hidden = true;
    root.dataset.notificationId = '';
    currentKey = null;
    document.documentElement.classList.remove('foms-drawing-alert-open');
  }

  // 사람별 상태(ack/read) 기록 — 알림 write helper(same-origin 헤더)를 거친다.
  function postState(notifId, path, reason) {
    if (!notifId || !window.FOMSNotificationWrite) return;
    try {
      window.FOMSNotificationWrite.fetch('/erp/api/notifications/' + encodeURIComponent(notifId) + '/' + path, {
        method: 'POST',
        headers: { 'Accept': 'application/json' }
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d || d.success !== true) {
            console.warn('[drawing-alert] ' + path + ' 실패:', d && (d.message || d.error));
          }
          if (path === 'read' && window.FOMSNotificationBadge &&
            typeof window.FOMSNotificationBadge.refresh === 'function') {
            window.FOMSNotificationBadge.refresh({ force: true, reason: reason });
          }
        })
        .catch(function (err) { console.warn('[drawing-alert] ' + path + ' 오류:', err); });
    } catch (e) {
      console.warn('[drawing-alert] write helper 오류:', e);
    }
  }

  function acknowledge(root, options) {
    var notifId = root.dataset.notificationId;
    var close = !options || options.close !== false;
    // 탭 간 닫기는 당일 실측만(도면 동작 불변 — 스펙 §5).
    if (notifId && root.dataset.kind === MEASURE_KIND) emit('foms:alert-ack', notifId);
    if (close) {
      hideRoot(root);
      showNext();
    }
    if (!notifId) return;
    ['ack', 'read'].forEach(function (path) { postState(notifId, path, 'drawing-alert-ack'); });
  }

  function fill(root, data) {
    var q = function (role) { return root.querySelector('[data-role="' + role + '"]'); };
    var openLink = q('open');
    var href;
    if (data.alert_kind === MEASURE_KIND) {
      // 당일 실측 긴급 추가 — 값은 전부 textContent(서버 값이라도 HTML 로 해석하지 않는다).
      q('kicker').textContent = '긴급 실측 추가';
      q('title').textContent = '오늘 ' + (data.time || '') + ' 실측 — ' + (data.customer_name || '');
      // 빈 칸은 빼고 잇는다 — 담당이 비면 "· 담당" 글자만 남았다(스테이징 실화면 2026-09-23).
      q('message').textContent = [data.area, data.manager ? '담당 ' + data.manager : ''].filter(Boolean).join(' · ');
      q('meta').textContent = [data.added_by ? data.added_by + ' 추가' : '', shortTime(data.added_at)].filter(Boolean).join(' · ');
      openLink.textContent = '주문 열기';
      href = safeOrderUrl(data.order_url);
    } else {
      q('kicker').textContent = data.title || '도면 수정 요청';
      var orderId = data.order_id || data.orderId;
      q('title').textContent =
        orderId ? ('주문 #' + orderId + ' 도면을 고쳐야 합니다') : '도면을 고쳐야 합니다';
      q('message').innerHTML = esc(data.message || '').replace(/\n/g, '<br>');
      var who = data.created_by_name || data.actor_name || '';
      q('meta').textContent = who ? (who + ' 요청') : '';
      openLink.textContent = '작업실에서 열기';
      href = deepLink(data);
    }
    root.dataset.kind = data.alert_kind || 'drawing';
    openLink.setAttribute('href', href || '#');
    openLink.hidden = !href;
  }

  function render(data, key) {
    var root = ensureRoot();
    currentKey = key;
    root.dataset.notificationId = key;
    fill(root, data);
    root.hidden = false;
    document.documentElement.classList.add('foms-drawing-alert-open');
    try { root.querySelector('[data-role="ack"]').focus(); } catch (e) { }
    beep(data.alert_kind);
    if (data.alert_kind === MEASURE_KIND) emit('foms:alert-shown', key);
  }

  function showNext() {
    var next = queue.shift();
    if (next) render(next.data, next.key);
  }

  function show(data) {
    if (!data || data.interrupt !== true) return false;
    var key = String(data.notification_id || data.id || '');
    if (key && shown[key]) return false;
    if (key) shown[key] = true;
    var root = document.getElementById(ROOT_ID);
    // 당일 실측이 끼면 대기열로 — 덮어쓰면 앞 알림이 확인되지 않는다. 도면끼리는 기존대로 덮는다.
    var busy = root && !root.hidden;
    if (busy && (data.alert_kind === MEASURE_KIND || root.dataset.kind === MEASURE_KIND)) queue.push({ key: key, data: data });
    else render(data, key);
    return true;
  }

  /** 다른 탭에서 확인한 알림을 닫는다(ack 는 다시 보내지 않는다). */
  function dismiss(notificationId) {
    var key = String(notificationId == null ? '' : notificationId);
    if (!key) return false;
    shown[key] = true;
    var root = document.getElementById(ROOT_ID);
    if (root && !root.hidden && currentKey === key) {
      hideRoot(root);
      showNext();
    } else {
      queue = queue.filter(function (item) { return item.key !== key; });
    }
    return true;
  }

  function markShown(id) { if (id != null && id !== '') shown[String(id)] = true; }

  var NOTICE_STACK_ID = 'foms-drawing-notices';

  function ensureNoticeStack() {
    var stack = document.getElementById(NOTICE_STACK_ID);
    if (stack) return stack;
    stack = document.createElement('div');
    stack.id = NOTICE_STACK_ID;
    stack.className = 'foms-drawing-notices';
    document.body.appendChild(stack);
    return stack;
  }

  /**
   * NOTICE 등급(수정 요청 취소 등): 작업을 막지 않는 쪽지. 자동으로 사라지지 않는다 —
   * 스스로 닫아야 읽음이 된다(자동 닫힘은 "못 본 채 사라짐"을 다시 만든다).
   */
  function notice(data) {
    if (!data || data.notice !== true) return false;
    var key = String(data.notification_id || data.id || '');
    if (key && shown[key]) return false;
    if (key) shown[key] = true;
    var stack = ensureNoticeStack();
    var card = document.createElement('div');
    card.className = 'foms-drawing-notice';
    var who = data.created_by_name || '';
    var href = deepLink(data);
    card.innerHTML = [
      '<p class="foms-drawing-notice__h">' + esc(data.title || '도면 수정요청 취소') + '</p>',
      '<p class="foms-drawing-notice__m">' + esc(data.message || '') + (who ? ' <span>(' + esc(who) + ')</span>' : '') + '</p>',
      '<div class="foms-drawing-notice__a">',
      href ? '  <a class="foms-drawing-notice__btn" data-role="open" href="' + esc(href) + '">주문 열기</a>' : '',
      '  <button type="button" class="foms-drawing-notice__btn foms-drawing-notice__btn--ghost" data-role="close">닫기</button>',
      '</div>'
    ].join('');
    card.addEventListener('click', function (e) {
      var t = e.target.closest('[data-role]');
      if (!t) return;
      postState(key, 'read', 'drawing-notice-read');
      if (t.dataset.role === 'close') card.remove();
    });
    stack.appendChild(card);
    return true;
  }

  function handle(data) {
    if (!data) return false;
    if (data.interrupt === true) return show(data);
    if (data.notice === true) return notice(data);
    return false;
  }

  function bindSocket(socket) {
    if (!socket || typeof socket.on !== 'function') return false;
    if (socket.__fomsDrawingAlertBound) return true;
    socket.__fomsDrawingAlertBound = true;
    socket.on('erp_notification', function (data) { handle(data); });
    return true;
  }

  window.FOMSDrawingAlert = {
    show: show, notice: notice, handle: handle, bindSocket: bindSocket,
    dismiss: dismiss, markShown: markShown
  };
})();
