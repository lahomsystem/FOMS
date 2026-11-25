/**
 * 도면 작업실 상세 요청사항 칸 — 공장 요청 [반영 완료] · [완료 해제] · [요청 반려](설계서 docs/specs/2026-11-25-production-stage-drawing-revision_SPEC.md
 * §2-2 · §10 · N4 · N5, D4).
 *
 * - [반영 완료] · [완료 해제] = POST /api/orders/<id>/drawing/fix/requests/<rid>/check {checked} — 막힘은 그대로(수정본이 가야 풀린다).
 * - [요청 반려] = 창 하나: 제목 "요청 반려" · 본문(서버가 data-confirm 에 실은 글 "반려 사유를 적어 주세요. 요청한 사람에게 알림이 가고,
 *   도면 3 막힘이 풀려요.") · 사유 칸(꼭 적기 — 비우면 "반려 사유를 적어 주세요.") · [취소] [요청 반려] → POST …/reject {note}.
 * - fetch 는 try/catch, data.success 로 판정. 되면 화면을 다시 읽는다(줄 · 막힘 · 공장 진행 · 주문 버전이 서버 값으로). 안 되면 서버 글을
 *   칸 아래 한 줄(반려 창이 열려 있으면 창 안)에.
 * - 창은 <dialog>(맨 위 층) — 모양은 D2 · D3 확인 창과 같은 dfx-dialog(workbench-fix.css).
 * - ERP 셸 조각이 다시 실행해도 한 번만 묶는다(G4 — window.__DW_FACTORY_REQUEST_BOUND).
 */
(function () {
  'use strict';
  if (window.__DW_FACTORY_REQUEST_BOUND) { return; }
  window.__DW_FACTORY_REQUEST_BOUND = true;

  var FAIL = '저장하지 못했어요. 잠시 뒤 다시 해 주세요.';
  var NOTE_REQUIRED = '반려 사유를 적어 주세요.';
  var busy = false;

  function node(tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) { el.className = cls; }
    if (text) { el.textContent = text; }
    return el;
  }

  async function post(orderId, rid, act, body) {
    var data = null;
    try {
      var url = '/api/orders/' + encodeURIComponent(orderId) + '/drawing/fix/requests/' + encodeURIComponent(rid) + '/' + act;
      var res = await fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(body)
      });
      try { data = await res.json(); } catch (_) { data = null; }
    } catch (e) {
      console.warn('[factory-request] post', e);
      return { ok: false, message: FAIL };
    }
    if (data && data.success === true) { return { ok: true }; }
    return { ok: false, message: (data && data.error) || FAIL };
  }

  function showError(box, message) {
    var el = box && box.querySelector('[data-dfr-error]');
    if (!el) { return; }
    el.textContent = message || '';
    el.hidden = !message;
  }

  /** [요청 반려] 창 — 사유를 적고 [요청 반려]를 누르면 send(사유)를 부른다(되면 다시 읽음, 안 되면 창 안에 서버 글). */
  function askReject(body, send) {
    var dialog = node('dialog', 'dfx-dialog dwp-dialog dfr-dialog');
    dialog.setAttribute('aria-label', '요청 반려');
    dialog.appendChild(node('div', 'dfx-dialog__head', '요청 반려'));
    var main = node('div', 'dfx-dialog__body');
    var text = node('p', 'dwp-dialog__text', body);
    text.setAttribute('id', 'dfr-reject-text');
    main.appendChild(text);
    var note = node('textarea', 'dfr-note-input');
    note.rows = 3;
    note.setAttribute('aria-labelledby', 'dfr-reject-text');
    main.appendChild(note);
    var err = node('p', 'dfx-error dfr-dialog-error');
    err.setAttribute('role', 'alert');
    err.hidden = true;
    main.appendChild(err);
    dialog.appendChild(main);
    var foot = node('div', 'dfx-dialog__foot');
    var cancel = node('button', 'dfx-btn dfx-btn--cancel', '취소');
    var go = node('button', 'dfx-btn dwp-btn--stop', '요청 반려');
    cancel.type = 'button';
    go.type = 'button';
    foot.appendChild(cancel);
    foot.appendChild(go);
    dialog.appendChild(foot);
    document.body.appendChild(dialog);
    function fail(message) { err.textContent = message; err.hidden = !message; }
    cancel.addEventListener('click', function () { if (!go.disabled) { dialog.close(); } });
    go.addEventListener('click', function () {
      var text = String(note.value || '').trim();
      if (!text) { fail(NOTE_REQUIRED); note.focus(); return; }
      fail('');
      go.disabled = true;
      cancel.disabled = true;
      send(text).then(function (res) {
        if (res.ok) { window.location.reload(); return; }
        go.disabled = false;
        cancel.disabled = false;
        fail(res.message);
      });
    });
    dialog.addEventListener('close', function () { dialog.remove(); });
    if (typeof dialog.showModal === 'function') { dialog.showModal(); } else { dialog.setAttribute('open', ''); }
    note.focus();
    return dialog;
  }

  function onClick(ev) {
    var btn = ev.target.closest ? ev.target.closest('[data-dfr-act]') : null;
    var box = btn && btn.closest('[data-dfr]');
    if (!box || busy) { return; }
    ev.preventDefault();
    var row = btn.closest('[data-dfr-row]');
    var orderId = box.getAttribute('data-order-id');
    var rid = row.getAttribute('data-request-id');
    showError(box, '');
    if (btn.getAttribute('data-dfr-act') === 'reject') {
      askReject(btn.getAttribute('data-confirm') || '', function (note) { return post(orderId, rid, 'reject', { note: note }); });
      return;
    }
    busy = true;
    btn.disabled = true;
    post(orderId, rid, 'check', { checked: btn.getAttribute('data-next-checked') === 'true' }).then(function (res) {
      if (res.ok) { window.location.reload(); return; }
      busy = false;
      btn.disabled = false;
      showError(box, res.message);
    });
  }

  document.addEventListener('click', onClick);
  window.FomsFactoryRequest = { askReject: askReject, post: post };
})();
