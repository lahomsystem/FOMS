/**
 * 도면 작업실 PC [긴급 호출] 버튼 + 전달 취소 경고 시트(#dwCancelWarnModal) — 사용자 결정 Q5-①④.
 *
 * - [data-dw-urgent-call] 은 공용 긴급 호출 창(urgent-call.js · window.fomsUrgentCall.open)을 연다
 *   (SPEC 2026-10-01 §4.3 — 도면 전용 #dwUrgentCallModal 은 지웠다). 버튼의 data-order-id 주문을 미리 고르고,
 *   data-urgent-team 팀을 먼저 보여 주고, data-urgent-message 로 사유를 미리 채운다.
 * - 전달 취소 경고 시트의 '영업에게 먼저 알리기': 시트를 닫은 뒤 같은 공용 창을 연다(두 창을 겹치지 않는다).
 * - [그래도 취소]는 전달 취소 API 를 곧바로 부른다(확인창을 두 번 띄우지 않는다).
 * - window.fomsDrawingCancelWarn(btn): 경고 시트 열기(폭별 문구 고르기). 인라인 cancelTransfer 가 이 JS 가 떴을 때만
 *   부르고, 안 떴으면 경고 문구 확인창으로 간다(시트만 열리고 [그래도 취소]가 죽는 일이 없게).
 */
(function () {
  'use strict';
  if (window.__FOMS_DRAWING_URGENT_PC_BOUND) return;
  window.__FOMS_DRAWING_URGENT_PC_BOUND = true;

  var WARN_ID = 'dwCancelWarnModal';

  function q(root, sel) { return root ? root.querySelector(sel) : null; }
  function attr(el, name) { return el ? String(el.getAttribute(name) || '') : ''; }
  function show(el, text) {
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('d-none', !text);
  }
  function modalApi() { return window.bootstrap && window.bootstrap.Modal ? window.bootstrap.Modal : null; }
  function notify(message) {
    if (typeof window.fomsShowToast === 'function') window.fomsShowToast(message);
    else window.alert(message);
  }

  function openUrgent(opener) {
    if (!window.fomsUrgentCall || typeof window.fomsUrgentCall.open !== 'function') {
      notify('긴급 호출 창을 열 수 없어요. 화면을 새로고침해 주세요.');
      return;
    }
    var warn = document.getElementById(WARN_ID);
    window.fomsUrgentCall.open({
      orderId: attr(opener, 'data-order-id') || attr(warn, 'data-order-id'),
      team: attr(opener, 'data-urgent-team'),
      message: attr(opener, 'data-urgent-message')
    });
  }

  function handleOpener(opener) {
    var api = modalApi();
    var openModal = opener.closest('.modal.show');
    if (openModal && api) {
      // 열린 시트(전달 취소 경고) 위에 창을 겹치지 않는다 — 닫힌 뒤 연다.
      openModal.addEventListener('hidden.bs.modal', function () { openUrgent(opener); }, { once: true });
      api.getOrCreateInstance(openModal).hide();
      return;
    }
    openUrgent(opener);
  }

  /**
   * 인라인 cancelTransfer 가 부른다: 보낸 회차면(서버가 싣는 폭별 문구가 있으면) 경고 시트를 열고 true.
   * 문구가 없거나 시트·Bootstrap 이 없으면 false — 부르는 쪽이 기존 확인창 경로로 간다.
   * @param {Element|null} cancelBtn #btn-cancel-transfer
   * @returns {boolean}
   */
  function openCancelWarn(cancelBtn) {
    var narrow = !!(window.matchMedia && window.matchMedia('(max-width: 991.98px)').matches);
    var text = attr(cancelBtn, narrow ? 'data-customer-sent-text-mobile' : 'data-customer-sent-text-pc')
      || attr(cancelBtn, 'data-customer-sent-text-pc') || attr(cancelBtn, 'data-customer-sent-text-mobile');
    var root = document.getElementById(WARN_ID);
    var api = modalApi();
    if (!text || !root || !api) return false;
    var textEl = q(root, '[data-cancel-warn-text]');
    if (textEl) textEl.textContent = text;
    show(q(root, '[data-cancel-warn-error]'), '');
    api.getOrCreateInstance(root).show();
    return true;
  }
  window.fomsDrawingCancelWarn = openCancelWarn;

  /** 전달 취소 경고 시트의 [그래도 취소]. */
  async function confirmCancelTransfer(btn) {
    if (btn.disabled) return;
    var root = document.getElementById(WARN_ID);
    var orderId = attr(root, 'data-order-id');
    var errEl = q(root, '[data-cancel-warn-error]');
    btn.disabled = true;
    show(errEl, '');
    try {
      var res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/cancel-transfer', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      var data = await res.json();
      if (!data || !data.success) {
        show(errEl, (data && data.message) || '전달 취소에 실패했어요');
        btn.disabled = false;
        return;
      }
      window.location.href = '/erp/drawing-workbench/' + encodeURIComponent(orderId) + '?tab=timeline';
    } catch (_) {
      show(errEl, '전달 취소 중 오류가 났어요. 잠시 뒤 다시 눌러 주세요.');
      btn.disabled = false;
    }
  }

  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest ? e.target : null;
    if (!t) return;
    var opener = t.closest('[data-dw-urgent-call]');
    if (opener) { e.preventDefault(); handleOpener(opener); return; }
    var cancelBtn = t.closest('[data-cancel-transfer-confirm]');
    if (cancelBtn) { e.preventDefault(); confirmCancelTransfer(cancelBtn); }
  });
})();
