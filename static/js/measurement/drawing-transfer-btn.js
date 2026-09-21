/**
 * STATE-CONTROLS-04 — 실측 대시보드 '도면 전달' 버튼.
 *
 * 이 버튼은 본공정 stage 를 MEASURE → DRAWING 으로 옮긴다. 새 API 는 없고
 * 기존 quest 승인(POST /api/orders/<id>/quest/approve)을 그대로 부른다.
 *
 * 축 구분: foms/api/drawing/erp_orders_drawing.py 의 도면 **파일** 전달은
 * drawing_status 축이고 stage 를 바꾸지 않는다. 이 파일은 본공정 stage 축이다 —
 * 두 축을 절대 섞지 마라.
 *
 * 노출/비활성 판정은 서버(foms/services/measurement/drawing_transfer_cta.py)가 한다.
 * 이 파일은 판정하지 않고, 매크로가 렌더한 .js-drawing-transfer 버튼을 배선만 한다.
 *
 * defer + 재로드 idempotent (window.__FOMS_DRAWING_TRANSFER_BTN_BOUND).
 */
(function () {
  'use strict';

  var SELECTOR = '.js-drawing-transfer';

  async function transferToDrawing(btn) {
    var orderId = btn.getAttribute('data-order-id');
    if (!orderId) return;
    if (btn.disabled) return;

    var confirmText = btn.getAttribute('data-confirm');
    if (confirmText && !window.confirm(confirmText)) return;

    btn.disabled = true;
    try {
      // 본문은 빈 객체다. 이 버튼은 data-team 을 달지 않고,
      // emergency_override / override_reason 도 보내지 않는다(ADMIN 전용·감사 의미가 다르다).
      var res = await fetch('/api/orders/' + orderId + '/quest/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      // 세션이 만료되면 login_required/role_required 가 JSON 이 아니라 로그인 페이지로
      // redirect 하고 fetch 가 그걸 따라간다. 그대로 json() 하면 사용자에게
      // "Unexpected token '<'" 가 뜨므로 상태코드별 한글 문장으로 바꾼다.
      var data;
      try {
        data = await res.json();
      } catch (parseError) {
        throw new Error(
          res.redirected || res.status === 401 || res.status === 403
            ? '로그인이 만료되었습니다. 새로고침 후 다시 시도하세요.'
            : '서버 응답을 읽을 수 없습니다 (HTTP ' + res.status + ')'
        );
      }
      if (!data.success) {
        // 관리자가 업무 게이트에 막혔으면 사유를 받아 한 번만 다시 보낸다(권한 축만 푼다).
        var ctl = window.FomsAdminOverride;
        var again = (ctl && typeof ctl.retry === 'function')
          ? await ctl.retry({
            url: '/api/orders/' + orderId + '/quest/approve',
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: {},
            code: data.code || '',
            message: data.message || data.error || ''
          })
          : null;
        if (again && again.ok) {
          data = again.data;
        } else {
          var failed = (again && again.data) || data;
          // 서버 code(COMMAND_REQUIRED·QUEST_INCOMPLETE·STAGE_CONFLICT)까지 노출해야 원인 파악이 된다.
          var detail = failed.code ? ' (' + failed.code + ')' : '';
          throw new Error((failed.message || failed.error || '도면 전달 실패') + detail);
        }
      }
      if (!data.auto_transitioned) {
        window.alert('승인은 기록됐지만 단계가 넘어가지 않았습니다. 관리자에게 확인하세요.');
      }
      window.location.reload();
    } catch (error) {
      btn.disabled = false;
      window.alert(String((error && error.message) || error || '도면 전달 중 오류가 발생했습니다.'));
    }
  }

  if (!window.__FOMS_DRAWING_TRANSFER_BTN_BOUND) {
    window.__FOMS_DRAWING_TRANSFER_BTN_BOUND = true;
    document.addEventListener('click', function (event) {
      var btn = event.target && event.target.closest
        ? event.target.closest(SELECTOR)
        : null;
      if (!btn) return;
      event.preventDefault();
      transferToDrawing(btn);
    });
  }
})();
