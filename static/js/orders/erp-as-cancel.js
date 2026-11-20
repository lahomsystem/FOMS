/**
 * AS 접수 취소 단추 배선 (설계서 2026-11-20-multi-item-split-schedule §4.4).
 *
 * 단추 = [data-erp-as-cancel][data-order-id] — 주문 화면 "본공정 단계" 줄(PC · 휴대폰)과 AS 화면 회차 차트
 * 현재 건 머리. 서버가 접수 상태 + 권한(관리자 · CS 능력)일 때만 그린다(as_cancel_allowed).
 *
 * 흐름: 누름 → 사유 묻기 → POST /api/orders/<id>/as/cancel {reason} → 끝나면 화면을 다시 읽는다.
 * 사유 창은 새로 만들지 않고 그 화면이 이미 쓰는 것을 쓴다 — 주문 화면은 공용 사유 시트
 * (window.FomsReasonSheet), 그 시트가 없는 AS 화면은 window.prompt(회차 판정과 같은 방식).
 *
 * 문서 위임 + 싱글턴 가드라 셸 조각이 다시 실려도 리스너가 쌓이지 않는다.
 */
(function () {
  'use strict';

  if (window.__FOMS_AS_CANCEL_BOUND) {
    return;
  }
  window.__FOMS_AS_CANCEL_BOUND = true;

  var BTN_SEL = '[data-erp-as-cancel]';
  var ASK_TEXT = '잘못 접수한 AS 를 취소합니다. 취소 사유를 적어 주세요.';

  function orderIdOf(btn) {
    var id = parseInt(btn.getAttribute('data-order-id') || '', 10);
    return id > 0 ? id : 0;
  }

  /**
   * 사유를 묻는다. 적으면 onReason(사유), 그만두면 아무것도 부르지 않는다.
   * @param {function(string): void} onReason
   */
  function askReason(onReason) {
    var sheet = window.FomsReasonSheet;
    if (sheet && typeof sheet.open === 'function' && document.querySelector('[data-foms-reason-sheet]')) {
      sheet.open({
        title: 'AS 접수 취소',
        actionLabel: '접수 취소',
        reasons: null,
        detailLabel: '취소 사유',
        requireDetail: true,
        onSubmit: function (_code, detail) {
          onReason(String(detail || '').trim());
        }
      });
      return;
    }
    var typed = window.prompt(ASK_TEXT, '');
    if (typed === null) {
      return;
    }
    var reason = String(typed).trim();
    if (!reason) {
      window.alert('취소 사유를 적어 주세요.');
      return;
    }
    onReason(reason);
  }

  /**
   * 취소 요청을 보낸다. 성공하면 화면을 다시 읽고, 실패하면 서버 글을 그대로 보인다.
   * @param {HTMLElement} btn
   * @param {number} orderId
   * @param {string} reason
   */
  async function sendCancel(btn, orderId, reason) {
    if (btn.getAttribute('data-busy') === '1') {
      return;
    }
    btn.setAttribute('data-busy', '1');
    btn.disabled = true;
    try {
      var res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/as/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
        body: JSON.stringify({ reason: reason })
      });
      var data = null;
      try {
        data = await res.json();
      } catch (_) {
        data = null;
      }
      if (!data || !data.success) {
        throw new Error((data && (data.error || data.message)) || 'AS 접수를 취소하지 못했습니다.');
      }
      window.location.reload();
    } catch (err) {
      window.alert(String((err && err.message) || err || 'AS 접수를 취소하지 못했습니다.'));
      btn.removeAttribute('data-busy');
      btn.disabled = false;
    }
  }

  document.addEventListener('click', function (event) {
    var target = event.target;
    var btn = target && target.closest ? target.closest(BTN_SEL) : null;
    if (!btn) {
      return;
    }
    event.preventDefault();
    var orderId = orderIdOf(btn);
    if (!orderId) {
      return;
    }
    askReason(function (reason) {
      sendCancel(btn, orderId, reason);
    });
  });
})();
