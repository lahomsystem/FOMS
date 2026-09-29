/**
 * 도면 방(모바일) 전달 취소 경고 시트 — 설계서 2026-09-29 §3.4 · 사용자 결정 Q4·Q5-④.
 *
 * 영업이 이번 회차를 고객에게 이미 보냈으면 서버가 경고 문구를 싣고, 모바일 [전달 취소]는
 * PC 버튼 대신 누르기 대신 #dwCancelWarnMobileModal 을 연다(workbench_mobile_handoff.html).
 *  - [영업에게 먼저 알리기 (긴급 호출)] → 시트를 닫은 뒤 기존 긴급 호출 시트(urgent-call-sheet.js 의
 *    [data-foms-urgent-call] 위임 처리)를 연다. 두 창이 겹쳐 초점을 다투지 않게 닫힘을 기다린다.
 *  - [그래도 취소] → POST /api/orders/<id>/cancel-transfer 한 번(확인창을 다시 띄우지 않는다, 막지 않음 Q4).
 *
 * 화면 조각 교체(erp-shell)로 다시 실행돼도 document 위임은 한 번만 건다(window.__…_BOUND).
 */
(function () {
  'use strict';
  if (window.__FOMS_DW_CANCEL_WARN_BOUND) return;
  window.__FOMS_DW_CANCEL_WARN_BOUND = true;

  var MODAL_ID = 'dwCancelWarnMobileModal';

  function notify(message, tone) {
    if (typeof window.fomsShowToast === 'function') {
      window.fomsShowToast(message, tone);
      return;
    }
    window.alert(message);
  }

  function modalInstance(modal) {
    if (!modal || !window.bootstrap || !window.bootstrap.Modal) return null;
    return window.bootstrap.Modal.getOrCreateInstance(modal);
  }

  function showError(modal, message) {
    var line = modal.querySelector('[data-dw-cancel-warn-error]');
    if (!line) {
      notify(message, 'error');
      return;
    }
    line.textContent = message;
    line.hidden = false;
  }

  /** 긴급 호출 시트를 연다 — 위임 처리가 받도록 문서 안에 잠깐 붙인 여는 버튼을 누른다. */
  function openUrgentCall(orderId) {
    if (!window.__FOMS_URGENT_CALL_BOUND) {
      notify('긴급 호출 창을 열 수 없어요. 화면을 새로고침한 뒤 다시 눌러 주세요.', 'error');
      return;
    }
    var opener = document.createElement('button');
    opener.type = 'button';
    opener.hidden = true;
    opener.setAttribute('data-foms-urgent-call', '');
    opener.setAttribute('data-order-id', orderId);
    document.body.appendChild(opener);
    try {
      opener.click();
    } finally {
      opener.remove();
    }
  }

  function askSalesFirst(modal) {
    var orderId = modal.getAttribute('data-order-id') || '';
    if (!orderId) return;
    var instance = modalInstance(modal);
    if (!instance) {
      openUrgentCall(orderId);
      return;
    }
    modal.addEventListener('hidden.bs.modal', function () { openUrgentCall(orderId); }, { once: true });
    instance.hide();
  }

  async function cancelTransferAnyway(modal, button) {
    if (button.disabled) return; // 두 번 누름 가드
    var orderId = modal.getAttribute('data-order-id') || '';
    if (!orderId) return;
    button.disabled = true;
    try {
      var res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/cancel-transfer', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { Accept: 'application/json' }
      });
      var data = await res.json();
      if (!data || !data.success) {
        showError(modal, (data && data.message) || '전달 취소에 실패했어요.');
        button.disabled = false;
        return;
      }
      notify(data.message || '전달을 취소했어요.', 'success');
      window.location.href = '/erp/drawing-workbench/' + encodeURIComponent(orderId) + '?tab=timeline';
    } catch (err) {
      console.error('[drawing-cancel-warn] 전달 취소 실패', err);
      showError(modal, '전달 취소 중 오류가 났어요. 잠시 뒤 다시 눌러 주세요.');
      button.disabled = false;
    }
  }

  document.addEventListener('click', function (event) {
    if (!event.target || !event.target.closest) return;
    var modal = event.target.closest('#' + MODAL_ID);
    if (!modal) return;

    if (event.target.closest('[data-dw-cancel-warn-urgent]')) {
      event.preventDefault();
      askSalesFirst(modal);
      return;
    }
    var confirmBtn = event.target.closest('[data-dw-cancel-warn-confirm]');
    if (confirmBtn) {
      event.preventDefault();
      cancelTransferAnyway(modal, confirmBtn);
    }
  });
})();
