/**
 * AI 상담 초안 [보내기] · [수정하기] 짧은 화면(templates/cs_agent/send.html — 플랜 C10-3 · 설계서 17.2.1 링크 길).
 *
 * 화면(GET)은 보여 주기만 한다. 이 스크립트가 서버가 data-* 로 실은 한 번용 서명 표를 POST 본문에 넣어 JSON API
 * (/api/cs-agent/turns/<id>/*)로 보낸다 — CSRF 토큰은 공용 csrf_bootstrap 의 fetch 래퍼가 붙인다.
 * 화면이 보인 때부터 [보내기]를 누를 때까지 밀리초(shown_ms)를 같이 보낸다('5초 안에 누름' 지표).
 * '확인 후 보내기'는 서버가 준 확인표를 다시 보내고, 고치는 칸이 바뀌면 그 확인표를 버린다(검수 R15-1).
 * 결과 모름(확인 중)이면 다시 보내지 않고 결과 맞추기(reconcile)를 몇 번 부른다. 글은 textContent 로만 넣는다.
 */
(function () {
  'use strict';
  if (window.__FOMS_CS_SEND_BOUND) return;
  window.__FOMS_CS_SEND_BOUND = true;

  var root = document.querySelector('[data-cs-send]');
  if (!root) return;
  var shownAt = Date.now();
  var busy = false;
  var confirmStamp = null;  // '확인 후 보내기' 확인표 — 경고를 본 그 글에만 맞는다(글을 고치면 버린다)
  var finished = false;
  var RECONCILE_EVERY_MS = 4000;
  var RECONCILE_TRIES = 20;
  var STATUS_EVERY_MS = 3000;
  var STATUS_TRIES = 40;

  function data(name) {
    return root.getAttribute('data-' + name) || '';
  }

  function message(kind, text) {
    var box = root.querySelector('[data-cs-send-msg]');
    if (!box) return;
    box.className = 'alert cs-send__msg alert-' + kind;
    box.textContent = text;
  }

  function showList(items) {
    var list = root.querySelector('[data-cs-send-warnings]');
    if (!list) return;
    while (list.firstChild) list.removeChild(list.firstChild);
    (items || []).forEach(function (item) {
      var li = document.createElement('li');
      li.textContent = (item && item.reason ? item.reason : '확인 필요') + (item && item.count > 1 ? ' (' + item.count + '곳)' : '');
      list.appendChild(li);
    });
    list.classList.toggle('d-none', !(items && items.length));
  }

  function setBusy(on) {
    busy = on;
    root.querySelectorAll('button').forEach(function (btn) {
      if (on) {
        btn.setAttribute('data-cs-was-disabled', btn.disabled ? '1' : '0');
        btn.disabled = true;
      } else if (btn.getAttribute('data-cs-was-disabled') === '0' && !finished) {
        btn.disabled = false;
      }
    });
  }

  function finish() {
    finished = true;
    root.querySelectorAll('button, textarea, input, select').forEach(function (el) { el.disabled = true; });
  }

  async function call(url, body) {
    var response;
    var payload = null;
    try {
      response = await fetch(url, {
        method: body ? 'POST' : 'GET',
        credentials: 'same-origin',
        headers: body ? { 'Content-Type': 'application/json', 'Accept': 'application/json' } : { 'Accept': 'application/json' },
        body: body ? JSON.stringify(body) : undefined
      });
    } catch (err) {
      return { ok: false, data: null, error: '서버에 닿지 못했습니다. 네트워크를 확인해 주세요.' };
    }
    try {
      payload = await response.json();
    } catch (err) {
      return { ok: false, data: null, error: '응답을 읽지 못했습니다. 다시 열어 주세요.' };
    }
    if (!payload || typeof payload !== 'object') {
      return { ok: false, data: null, error: '응답을 읽지 못했습니다. 다시 열어 주세요.' };
    }
    return { ok: payload.success === true, data: payload.data || null, error: payload.error || '' };
  }

  function wait(ms) {
    return new Promise(function (resolve) { window.setTimeout(resolve, ms); });
  }

  async function reconcileLoop() {
    for (var i = 0; i < RECONCILE_TRIES; i += 1) {
      await wait(RECONCILE_EVERY_MS);
      var res = await call(data('reconcile-url'), { token: data('token') });
      var code = res.data && res.data.code;
      if (code === 'sent') { message('success', res.data.message); finish(); return; }
      if (code === 'failed') { message('danger', res.data.message); finished = false; setBusy(false); return; }
      if (code && code !== 'checking') { message('warning', res.data.message || res.error); finish(); return; }
      if (!res.data && res.error) { message('warning', res.error); }
    }
    message('warning', '아직 확인되지 않았어요 — 데스크에서 손님 쪽에 갔는지 보고, 이 화면을 다시 열어 주세요.');
  }

  function handleSend(res) {
    var d = res.data || {};
    var code = d.code;
    showList([]);
    if (code === 'sent') { message('success', d.message); finish(); return; }
    if (code === 'checking') { message('info', d.message); finish(); reconcileLoop(); return; }
    if (code === 'needs_confirm') {
      confirmStamp = d.confirm || null;
      showList(d.warnings);
      message('warning', d.message);
      var go = root.querySelector('[data-cs-send-go]');
      if (go) go.textContent = '확인 후 보내기';
      return;
    }
    if (code === 'blocked') { showList(d.problems); message('danger', d.message); return; }
    if (code === 'new_message' || code === 'already' || code === 'not_open' || code === 'discarded') {
      message('warning', d.message);
      finish();
      return;
    }
    message('danger', d.message || res.error || '보내지 못했습니다.');
  }

  async function onSend() {
    if (busy || finished) return;
    var body = { token: data('token'), mode: 'as_is', confirm: confirmStamp, shown_ms: Math.max(0, Date.now() - shownAt) };
    if (data('mode') === 'edit') {
      var text = root.querySelector('[data-cs-send-text]');
      var reason = root.querySelector('[data-cs-send-reason]');
      body.mode = 'edited';
      body.text = text ? text.value : '';
      body.edit_reason = reason ? reason.value : '';
      if (!body.text.trim()) { message('warning', '보낼 글이 비었어요.'); return; }
      if (!body.edit_reason) { message('warning', '고친 까닭을 골라 주세요.'); return; }
    }
    setBusy(true);
    message('info', '보내는 중이에요…');
    var res = await call(data('send-url'), body);
    setBusy(false);
    handleSend(res);
  }

  async function onDiscard() {
    if (busy || finished) return;
    if (!window.confirm('이 초안을 버릴까요? 손님께는 아무것도 가지 않아요.')) return;
    setBusy(true);
    var res = await call(data('discard-url'), { token: data('token') });
    setBusy(false);
    var d = res.data || {};
    message(res.ok ? 'secondary' : 'warning', d.message || res.error || '버리지 못했습니다.');
    if (res.ok || d.code === 'already') finish();
  }

  async function waitForRewrite() {
    var before = data('memo-id');
    for (var i = 0; i < STATUS_TRIES; i += 1) {
      await wait(STATUS_EVERY_MS);
      var res = await call(data('status-url'), null);
      var d = res.data || {};
      if (res.ok && d.memo_id && d.memo_id !== before) { window.location.reload(); return; }
      if (res.ok && d.rewrite_state === 'failed') {
        message('warning', 'AI 가 다시 쓰지 못했어요 — 직접 고쳐 보내 주세요.');
        setBusy(false);
        return;
      }
    }
    message('warning', '다시 쓰기가 늦어요 — 직접 고쳐 보내거나 잠시 뒤 다시 열어 주세요.');
    setBusy(false);
  }

  async function onRewrite() {
    if (busy || finished) return;
    var note = root.querySelector('[data-cs-rewrite-note]');
    var text = note ? note.value.trim() : '';
    if (!text) { message('warning', '고칠 말을 적어 주세요.'); return; }
    setBusy(true);
    var res = await call(data('rewrite-url'), { token: data('token'), note: text });
    var d = res.data || {};
    if (d.code === 'rewrite_requested') {
      message('info', d.message);
      busy = true;
      waitForRewrite();
      return;
    }
    setBusy(false);
    message('warning', d.message || res.error || '요청하지 못했습니다.');
  }

  function bind(selector, handler) {
    var el = root.querySelector(selector);
    if (el) el.addEventListener('click', handler);
  }

  function resetConfirm() {
    if (!confirmStamp) return;
    confirmStamp = null;  // 글이 바뀌었다 — 새 글의 경고를 다시 본다
    showList([]);
    var go = root.querySelector('[data-cs-send-go]');
    if (go) go.textContent = '보내기';
  }

  var box = root.querySelector('[data-cs-send-text]');
  if (box) box.addEventListener('input', resetConfirm);
  bind('[data-cs-send-go]', onSend);
  bind('[data-cs-discard]', onDiscard);
  bind('[data-cs-rewrite-go]', onRewrite);
  if (data('checking') === '1' && data('token')) reconcileLoop();
})();
