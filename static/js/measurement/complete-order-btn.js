/**
 * STATE-CONTROLS-02 — 물류/실측 대시보드 canonical COMPLETE 컨트롤.
 *
 * status_select_options.html 의 complete_order_control 매크로가 렌더한
 * .js-complete-order 버튼을 전역 위임으로 배선한다. confirm 후
 * field_update(status=COMPLETED) 호출 — 선택자 시절과 동일한 백엔드 경로.
 * defer + 재로드 idempotent (window.__FOMS_COMPLETE_ORDER_BTN_BOUND).
 */
(function () {
  'use strict';

  function completeOrder(btn) {
    var orderId = btn.getAttribute('data-order-id');
    if (!orderId) return;
    if (!window.confirm('주문 #' + orderId + '을(를) "완료" 상태로 변경할까요?')) {
      return;
    }
    btn.disabled = true;
    fetch('/api/update_order_field', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        order_id: orderId,
        field_name: 'status',
        new_value: 'COMPLETED'
      })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.success) {
          window.location.reload();
          return;
        }
        var msg = (data && (data.message || data.error)) || '완료 처리에 실패했습니다.';
        window.alert(msg);
        btn.disabled = false;
      })
      .catch(function () {
        window.alert('서버 통신 중 오류가 발생했습니다.');
        btn.disabled = false;
      });
  }

  if (!window.__FOMS_COMPLETE_ORDER_BTN_BOUND) {
    window.__FOMS_COMPLETE_ORDER_BTN_BOUND = true;
    document.addEventListener('click', function (e) {
      var btn = e.target && e.target.closest
        ? e.target.closest('.js-complete-order')
        : null;
      if (btn) completeOrder(btn);
    });
  }
})();
