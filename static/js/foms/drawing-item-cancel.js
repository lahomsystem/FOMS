/**
 * 확정 뒤 제품 취소 창(#dwItemCancelModal) — DRAWING-PARTIAL-CONFIRM 6단계.
 * 설계서 docs/specs/2026-10-12-drawing-confirm-partial-cancel_SPEC.md §10.
 *
 * - POST /api/orders/<id>/items/<uid>/cancel {reason, note} + If-Match(mutation_version) + Idempotency-Key.
 * - 성공하면 도면 탭에 머문 채 새로 읽는다. 실패면 아무것도 안 바뀌었고 사유만 보인다.
 */
(function () {
  'use strict';
  if (window.__FOMS_DRAWING_ITEM_CANCEL_BOUND) return;
  window.__FOMS_DRAWING_ITEM_CANCEL_BOUND = true;

  var MODAL_ID = 'dwItemCancelModal';
  var target = { uid: '', name: '' };
  var busy = false;

  function q(root, sel) { return root ? root.querySelector(sel) : null; }
  function showError(root, text) {
    var el = q(root, '[data-item-cancel-error]');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('d-none', !text);
  }
  function key() {
    try { if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID(); } catch (_) { /* 아래 대체 */ }
    return 'dwic-' + Date.now() + '-' + Math.random().toString(36).slice(2, 12);
  }

  async function submit(root) {
    if (busy || !target.uid) return;
    var reasonEl = q(root, 'input[name="dw-item-cancel-reason"]:checked');
    var reason = reasonEl ? reasonEl.value : '';
    var note = String((q(root, '#dw-item-cancel-note') || {}).value || '').trim();
    if (reason === 'other' && !note) { showError(root, "'기타' 사유는 메모를 적어 주세요."); return; }
    var orderId = root.getAttribute('data-order-id') || '';
    var version = root.getAttribute('data-mutation-version') || '';
    var btn = q(root, '[data-item-cancel-submit]');
    busy = true;
    if (btn) btn.disabled = true;
    showError(root, '');
    var data = {};
    try {
      var headers = { 'Content-Type': 'application/json', Accept: 'application/json', 'Idempotency-Key': key() };
      if (version) headers['If-Match'] = version;
      var res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/items/' + encodeURIComponent(target.uid) + '/cancel', {
        method: 'POST', credentials: 'same-origin', headers: headers,
        body: JSON.stringify({ reason: reason, note: note || null }),
      });
      try { data = await res.json(); } catch (_) { data = {}; }
      if (!data.success) throw new Error(data.error || ('HTTP ' + res.status));
    } catch (err) {
      showError(root, '취소하지 못했어요 — ' + (err && err.message ? err.message : '네트워크 오류'));
      busy = false;
      if (btn) btn.disabled = false;
      return;
    }
    if (typeof window.fomsShowToast === 'function') window.fomsShowToast(target.name + ' 취소했어요');
    window.location.reload();
  }

  document.addEventListener('show.bs.modal', function (e) {
    var root = e.target;
    if (!root || root.id !== MODAL_ID) return;
    var opener = e.relatedTarget;
    target.uid = opener ? (opener.getAttribute('data-item-cancel-uid') || '') : '';
    target.name = opener ? (opener.getAttribute('data-item-cancel-name') || '') : '';
    var title = q(root, '[data-item-cancel-title]');
    if (title) title.textContent = (target.name || '제품') + '을(를) 취소할까요?';
    var note = q(root, '#dw-item-cancel-note');
    if (note) note.value = '';
    var first = q(root, '#dw-item-cancel-customer');
    if (first) first.checked = true;
    var btn = q(root, '[data-item-cancel-submit]');
    if (btn) btn.disabled = false;
    busy = false;
    showError(root, '');
  });
  document.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('[data-item-cancel-submit]') : null;
    if (!btn) return;
    e.preventDefault();
    submit(document.getElementById(MODAL_ID));
  });
})();
