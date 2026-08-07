/**
 * STATE-CONTROLS-02/03 — 물류/실측 대시보드 canonical 완료 컨트롤.
 *
 * status_select_options.html 의 complete_order_control / as_complete_control 매크로가
 * 렌더한 .js-complete-order 버튼을 전역 위임으로 배선한다. 어떤 필드를 쓰는지는
 * 버튼이 data-field/data-value 로 선언한다:
 *   - 일반 완료: field=status,            value=COMPLETED
 *   - AS 완료  : field=as_completed_date, value=오늘(YYYY-MM-DD)
 * AS 완료가 status 를 직접 쓰지 않는 이유는 AS 완료 탭 조건이 status+as_completed_date
 * 동시 충족이고, canonical AS cycle 만 그 둘을 한 트랜잭션으로 채우기 때문이다.
 *
 * defer + 재로드 idempotent (window.__FOMS_COMPLETE_ORDER_BTN_BOUND).
 */
(function () {
  'use strict';

  function completeOrder(btn) {
    var orderId = btn.getAttribute('data-order-id');
    var field = btn.getAttribute('data-field') || 'status';
    var value = btn.getAttribute('data-value') || 'COMPLETED';
    var confirmMsg = btn.getAttribute('data-confirm')
      || ('주문 #' + orderId + '을(를) 완료 처리할까요?');
    if (!orderId) return;
    if (!window.confirm(confirmMsg)) return;

    btn.disabled = true;
    fetch('/api/update_order_field', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        order_id: orderId,
        field_name: field,
        new_value: value
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
