/**
 * 도면 작업실 실행판 'AS 도면' 카드(#dw-as-card) — 완료 주문 AS 도면.
 * 설계서 docs/specs/2026-11-11-as-drawing-after-completion_SPEC.md §4.
 *
 * - [AS 도면 시작]   POST /api/orders/<id>/drawing/as/start
 *                    AS 접수가 없으면 접수까지 하고, 체크가 켜져 있으면 채널톡 AS방 접수
 *                    (지금 AS PUSH: POST /api/channel/push-manual push_kind='as')를 잇는다.
 * - [AS 도면 보내기] POST .../drawing/as/transfer
 * - [확인했어요]     POST .../drawing/as/confirm
 * - [고쳐 주세요]    POST .../drawing/as/request-revision {reason}
 * - [그만두기]       POST .../drawing/as/cancel
 * 성공하면 화면을 다시 읽는다(카드·목록 칸이 서버 값으로 맞춰진다).
 */
(function () {
  'use strict';
  if (window.__FOMS_DRAWING_AS_BOUND) return;
  window.__FOMS_DRAWING_AS_BOUND = true;

  function card() { return document.getElementById('dw-as-card'); }

  function setStatus(text, ok) {
    var el = card() && card().querySelector('[data-dw-as-status]');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('d-none', !text);
    el.classList.toggle('text-success', !!ok);
    el.classList.toggle('text-danger', !ok);
  }

  async function post(url, body) {
    var data = {};
    try {
      var res = await fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(body || {}),
      });
      try { data = await res.json(); } catch (_) { data = {}; }
    } catch (e) {
      data = { success: false, error: '인터넷 연결을 확인해 주세요.' };
    }
    if (!data || !data.success) {
      return { ok: false, message: (data && (data.error || data.message)) || '저장하지 못했어요. 잠시 뒤 다시 해 주세요.' };
    }
    return { ok: true, data: data.data || data };
  }

  function base() {
    var c = card();
    return c ? '/api/orders/' + encodeURIComponent(c.getAttribute('data-order-id') || '') : '';
  }

  function reloadSoon(ms) { window.setTimeout(function () { window.location.reload(); }, ms || 600); }

  async function pushChannel() {
    var c = card();
    var orderId = Number(c.getAttribute('data-order-id') || 0);
    return post('/api/channel/push-manual', { order_id: orderId, push_kind: 'as' });
  }

  async function start(form, btn) {
    var contentEl = form.querySelector('[data-dw-as-content]');
    var memoEl = form.querySelector('[data-dw-as-memo]');
    var channelEl = form.querySelector('[data-dw-as-channel]');
    var body = { memo: memoEl ? memoEl.value.trim() : '' };
    if (contentEl) {
      var content = contentEl.value.trim();
      if (!content) {
        setStatus('AS 내용을 적어 주세요.', false);
        contentEl.focus();
        return;
      }
      body.as_register = { content: content };
    }
    btn.disabled = true;
    setStatus('저장하고 있어요…', true);
    var r = await post(base() + '/drawing/as/start', body);
    if (!r.ok) {
      btn.disabled = false;
      setStatus(r.message, false);
      return;
    }
    if (r.data && r.data.registered_as && channelEl && channelEl.checked) {
      var p = await pushChannel();
      if (!p.ok) {
        setStatus('AS 접수와 도면 시작은 됐어요. 채널톡 AS방 접수는 못 했어요: ' + p.message
          + ' 카드의 [채널톡 AS방에 접수 올리기]로 다시 보내 주세요.', false);
        reloadSoon(3500);
        return;
      }
      setStatus('AS 접수, AS 도면 시작, 채널톡 AS방 접수를 했어요.', true);
    } else {
      setStatus('AS 도면을 시작했어요. [AS 도면 그리기]로 마법사를 여세요.', true);
    }
    reloadSoon(1200);
  }

  var ACTIONS = {
    transfer: function (btn) {
      var n = btn.getAttribute('data-count') || '';
      if (!window.confirm('AS 도면 ' + n + '장을 영업 담당과 AS 담당에게 보내요.\n원래 최종 도면은 그대로예요.')) return null;
      return post(base() + '/drawing/as/transfer', {});
    },
    confirm: function () {
      if (!window.confirm('이 AS 도면을 확인했어요. 도면팀에 알려요.')) return null;
      return post(base() + '/drawing/as/confirm', {});
    },
    revision: function () {
      var el = card().querySelector('#dw-as-revision-reason');
      var reason = el ? el.value.trim() : '';
      if (!reason) {
        setStatus('무엇을 고쳐야 하는지 적어 주세요.', false);
        if (el) el.focus();
        return null;
      }
      return post(base() + '/drawing/as/request-revision', { reason: reason });
    },
    cancel: function () {
      if (!window.confirm('AS 도면을 그만둬요. 함께 만든 AS 접수는 남아요.')) return null;
      return post(base() + '/drawing/as/cancel', {});
    },
    channel: function () { return pushChannel(); },
  };

  var DONE_TEXT = {
    transfer: '보냈어요. 영업 담당과 AS 담당이 확인해요.',
    confirm: '확인했어요.',
    revision: '고쳐 달라고 보냈어요.',
    cancel: 'AS 도면을 그만뒀어요.',
    channel: '채널톡 AS방에 접수를 올렸어요.',
  };

  async function act(name, btn) {
    if (name === 'revision-open') {
      var form = card().querySelector('[data-dw-as-revision-form]');
      if (form) {
        form.classList.remove('d-none');
        var ta = form.querySelector('textarea');
        if (ta) ta.focus();
      }
      return;
    }
    var run = ACTIONS[name];
    if (!run) return;
    var pending = run(btn);
    if (!pending) return;
    btn.disabled = true;
    var r = await pending;
    if (!r.ok) {
      btn.disabled = false;
      setStatus(r.message, false);
      return;
    }
    setStatus(DONE_TEXT[name] || '저장했어요.', true);
    reloadSoon(900);
  }

  document.addEventListener('click', function (ev) {
    var t = ev.target && ev.target.closest ? ev.target : null;
    if (!t) return;
    var opener = t.closest('[data-dw-as-start-open]');
    if (opener) {
      var form = card() && card().querySelector('[data-dw-as-start-form]');
      if (!form) return;
      ev.preventDefault();
      form.classList.remove('d-none');
      card().scrollIntoView({ block: 'nearest' });
      var first = form.querySelector('textarea, input');
      if (first) first.focus();
      return;
    }
    var closer = t.closest('[data-dw-as-start-close]');
    if (closer) {
      var f = closer.closest('[data-dw-as-start-form]');
      if (f) f.classList.add('d-none');
      return;
    }
    var btn = t.closest('[data-dw-as-act]');
    if (!btn || !btn.closest('#dw-as-card')) return;
    ev.preventDefault();
    act(btn.getAttribute('data-dw-as-act'), btn);
  });

  document.addEventListener('submit', function (ev) {
    var form = ev.target && ev.target.closest ? ev.target.closest('[data-dw-as-start-form]') : null;
    if (!form) return;
    ev.preventDefault();
    var btn = form.querySelector('button[type="submit"]');
    if (btn && !btn.disabled) start(form, btn);
  });
})();
