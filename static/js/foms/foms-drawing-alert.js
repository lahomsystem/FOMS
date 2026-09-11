/**
 * 도면 수정 요청 확인창 (ACTION-REQUIRED 등급).
 *
 * 왜: 도면팀은 하루를 도면 작업실·마법사에서 보내는데, 수정 요청 알림은 상단 종 배지로만
 * 왔다. 2026-09-11 운영 실측에서 90일 수정 요청 21건 중 8건(38%)이 아무도 열지 않은 채
 * 남았고, 알림을 여는 데 평균 최대 91.9시간이 걸렸다. 긴급 호출(P0)의 전체화면 빨강
 * 오버레이는 "지금 당장 사람을 부르는" 등급이라 수정 요청에 쓰면 과하다. 그 사이 등급으로
 * **확인을 눌러야 닫히는 중앙 확인창**을 둔다.
 *
 * 등급 판정은 서버가 한다 — payload 의 `interrupt === true` 만 이 창을 띄운다.
 * 확인 클릭 = ack(+read) 이므로, 지금 0건인 확인 기록이 사람의 행동으로 채워진다.
 *
 * 등급은 둘이다:
 *   - `interrupt: true` → 중앙 확인창(확인을 눌러야 닫힘, ack 기록). 수정 요청.
 *   - `notice: true`    → 오른쪽 아래 쪽지(작업을 막지 않음, 닫으면 읽음). 수정 요청 취소.
 *
 * 사용: window.FOMSDrawingAlert.show(payload) / .notice(payload) / .bindSocket(socket)
 */
(function () {
  'use strict';

  if (window.FOMSDrawingAlert) {
    return;
  }

  var ROOT_ID = 'foms-drawing-alert';
  var shown = Object.create(null);

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function beep() {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      var ctx = new Ctx();
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = 'sine';
      osc.frequency.setValueAtTime(660, ctx.currentTime);
      gain.gain.setValueAtTime(0.07, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.28);
      osc.start();
      osc.stop(ctx.currentTime + 0.3);
    } catch (e) {
      /* 소리는 부가 신호다 — 실패해도 창은 뜬다. */
    }
  }

  function deepLink(data) {
    var orderId = data && (data.order_id || data.orderId);
    if (!orderId) return '';
    return '/erp/drawing-workbench/' + encodeURIComponent(orderId) + '?tab=requests';
  }

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

  function acknowledge(root, options) {
    var notifId = root.dataset.notificationId;
    var close = !options || options.close !== false;
    if (close) {
      root.hidden = true;
      document.documentElement.classList.remove('foms-drawing-alert-open');
    }
    if (!notifId || !window.FOMSNotificationWrite) return;
    var base = '/erp/api/notifications/' + encodeURIComponent(notifId) + '/';
    ['ack', 'read'].forEach(function (path) {
      try {
        window.FOMSNotificationWrite.fetch(base + path, {
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
              window.FOMSNotificationBadge.refresh({ force: true, reason: 'drawing-alert-ack' });
            }
          })
          .catch(function (err) { console.warn('[drawing-alert] ' + path + ' 오류:', err); });
      } catch (e) {
        console.warn('[drawing-alert] write helper 오류:', e);
      }
    });
  }

  function show(data) {
    if (!data || data.interrupt !== true) return false;
    var key = String(data.notification_id || data.id || '');
    if (key && shown[key]) return false;
    if (key) shown[key] = true;

    var root = ensureRoot();
    root.dataset.notificationId = key;
    root.querySelector('[data-role="kicker"]').textContent = data.title || '도면 수정 요청';
    var orderId = data.order_id || data.orderId;
    root.querySelector('[data-role="title"]').textContent =
      orderId ? ('주문 #' + orderId + ' 도면을 고쳐야 합니다') : '도면을 고쳐야 합니다';
    root.querySelector('[data-role="message"]').innerHTML = esc(data.message || '')
      .replace(/\n/g, '<br>');
    var who = data.created_by_name || data.actor_name || '';
    root.querySelector('[data-role="meta"]').textContent = who ? (who + ' 요청') : '';
    var openLink = root.querySelector('[data-role="open"]');
    var href = deepLink(data);
    if (href) {
      openLink.setAttribute('href', href);
      openLink.hidden = false;
    } else {
      openLink.hidden = true;
    }

    root.hidden = false;
    document.documentElement.classList.add('foms-drawing-alert-open');
    try { root.querySelector('[data-role="ack"]').focus(); } catch (e) { }
    beep();
    return true;
  }

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

  function markRead(notifId) {
    if (!notifId || !window.FOMSNotificationWrite) return;
    try {
      window.FOMSNotificationWrite.fetch(
        '/erp/api/notifications/' + encodeURIComponent(notifId) + '/read',
        { method: 'POST', headers: { 'Accept': 'application/json' } }
      )
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d && d.success && window.FOMSNotificationBadge &&
            typeof window.FOMSNotificationBadge.refresh === 'function') {
            window.FOMSNotificationBadge.refresh({ force: true, reason: 'drawing-notice-read' });
          }
        })
        .catch(function (err) { console.warn('[drawing-notice] read 오류:', err); });
    } catch (e) {
      console.warn('[drawing-notice] write helper 오류:', e);
    }
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
      markRead(key);
      if (t.dataset.role === 'close') {
        card.remove();
      }
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
    show: show, notice: notice, handle: handle, bindSocket: bindSocket
  };
})();
