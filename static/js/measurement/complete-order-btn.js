/**
 * STATE-CONTROLS-02/03 — 물류/실측 대시보드 canonical 완료 컨트롤.
 *
 * status_select_options.html 의 complete_order_control / as_complete_control 매크로가
 * 렌더한 .js-complete-order 버튼을 전역 위임으로 배선한다. 어떤 필드를 쓰는지는
 * 버튼이 data-field/data-value 로 선언한다:
 *   - 일반 완료: field=status,            value=COMPLETED
 *   - AS 완료  : field=as_completed_date, value=오늘(YYYY-MM-DD)
 * C-B1(2026-09-20): 메인 파이프라인 주문의 최종 완료는 서버가 data-complete-endpoint=
 * "cs_complete" 로 표시하고, 그때는 정식 경로 POST /api/orders/<id>/cs/complete 를 부른다
 * (body 없음). 그 밖에는 기존 field_update 경로 그대로다.
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

    var endpoint = btn.getAttribute('data-complete-endpoint') || '';
    var url = '/api/update_order_field';
    var payload = { order_id: orderId, field_name: field, new_value: value };
    if (endpoint === 'cs_complete') {
      url = '/api/orders/' + encodeURIComponent(orderId) + '/cs/complete';
      payload = {};
    }

    var headers = { 'Content-Type': 'application/json' };
    btn.disabled = true;
    fetch(url, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify(payload)
    })
      .then(function (r) {
        return r.json().catch(function () { return null; });
      })
      .then(function (data) {
        if (data && data.success) {
          window.location.reload();
          return null;
        }
        // 관리자가 업무 게이트(완료 경로·역행 차단)에 막혔으면 사유를 받아 한 번만 다시 보낸다.
        return askAdminOverride(url, headers, payload, data).then(function (retried) {
          if (retried && retried.ok) {
            window.location.reload();
            return null;
          }
          var failed = (retried && retried.data) || data;
          var msg = (failed && (failed.message || failed.error)) || '완료 처리에 실패했습니다.';
          window.alert(msg);
          btn.disabled = false;
          return null;
        });
      })
      .catch(function () {
        window.alert('서버 통신 중 오류가 발생했습니다.');
        btn.disabled = false;
      });
  }

  /**
   * 거부 응답을 공용 재시도 컨트롤러에 넘긴다.
   * 컨트롤러가 없거나(스크립트 미배선) 관리자가 아니면 아무것도 하지 않는다 — 호출부가 원래 오류를 띄운다.
   */
  function askAdminOverride(url, headers, payload, data) {
    var ctl = window.FomsAdminOverride;
    if (!ctl || typeof ctl.retry !== 'function') {
      return Promise.resolve(null);
    }
    return ctl.retry({
      url: url,
      method: 'POST',
      headers: headers,
      body: payload,
      code: (data && data.code) || '',
      message: (data && (data.message || data.error)) || ''
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
