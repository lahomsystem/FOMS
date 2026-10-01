/**
 * 도면 방(모바일) 전달 취소 경고 시트 — 설계서 2026-09-29 §3.4 · 사용자 결정 Q4·Q5-④.
 *
 * 영업이 이번 회차를 고객에게 이미 보냈으면 서버가 경고 문구를 싣고, 모바일 [전달 취소]는
 * PC 버튼 대신 누르기 대신 #dwCancelWarnMobileModal 을 연다(workbench_mobile_handoff.html).
 *  - [영업에게 먼저 알리기 (긴급 호출)] → 시트를 닫은 뒤 공용 긴급 호출 창(urgent-call.js ·
 *    window.fomsUrgentCall.open)을 이 주문 · 영업팀 · 버튼의 data-urgent-message 사유로 연다.
 *    두 창이 겹쳐 초점을 다투지 않게 닫힘을 기다린다. 받는 사람은 사용자가 고른다.
 *  - [그래도 취소] → POST /api/orders/<id>/cancel-transfer 한 번(확인창을 다시 띄우지 않는다, 막지 않음 Q4).
 *
 * 화면 조각 교체(erp-shell)로 다시 실행돼도 document 위임은 한 번만 건다(window.__…_BOUND).
 */
(function () {
  'use strict';
  if (window.__FOMS_DW_CANCEL_WARN_BOUND) return;
  window.__FOMS_DW_CANCEL_WARN_BOUND = true;

  var MODAL_ID = 'dwCancelWarnMobileModal';
  var MAX_MESSAGE = 500; // urgent-call.js 와 같은 사유 길이 상한

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

  /**
   * 공용 긴급 호출 창(urgent-call.js · window.fomsUrgentCall)을 이 주문 · 영업팀 · 미리 쓴 사유로 연다.
   */
  function openUrgentCall(orderId, message) {
    if (!window.fomsUrgentCall || typeof window.fomsUrgentCall.open !== 'function') {
      notify('긴급 호출 창을 열 수 없어요. 화면을 새로고침한 뒤 다시 눌러 주세요.', 'error');
      return;
    }
    window.fomsUrgentCall.open({
      orderId: orderId,
      team: 'SALES',
      message: String(message || '').slice(0, MAX_MESSAGE)
    });
  }

  /**
   * 경고 시트를 닫은 뒤 긴급 호출 시트를 연다(두 창이 초점을 다투지 않게).
   * 시트가 아직 열리는 중이면 Bootstrap 이 hide() 를 무시한다 — 다 열린 뒤(shown) 다시 닫는다.
   * 기다리는 동안 버튼을 잠가 리스너가 쌓이지 않게 한다(여러 번 눌러도 한 번).
   */
  function askSalesFirst(modal, button) {
    var orderId = modal.getAttribute('data-order-id') || '';
    if (!orderId || modal.__fomsAskPending) return;
    var message = button ? button.getAttribute('data-urgent-message') || '' : '';
    var instance = modalInstance(modal);
    if (!instance || !modal.classList.contains('show')) {
      openUrgentCall(orderId, message);
      return;
    }
    modal.__fomsAskPending = true;
    if (button) button.disabled = true;
    function hideNow() { instance.hide(); }
    modal.addEventListener('shown.bs.modal', hideNow, { once: true });
    modal.addEventListener('hidden.bs.modal', function () {
      modal.removeEventListener('shown.bs.modal', hideNow);
      modal.__fomsAskPending = false;
      if (button) button.disabled = false;
      openUrgentCall(orderId, message);
    }, { once: true });
    hideNow();
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

    var urgentBtn = event.target.closest('[data-dw-cancel-warn-urgent]');
    if (urgentBtn) {
      event.preventDefault();
      askSalesFirst(modal, urgentBtn);
      return;
    }
    var confirmBtn = event.target.closest('[data-dw-cancel-warn-confirm]');
    if (confirmBtn) {
      event.preventDefault();
      cancelTransferAnyway(modal, confirmBtn);
    }
  });
})();
