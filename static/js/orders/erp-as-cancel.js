/**
 * AS 접수 취소 단추 배선 (설계서 2026-11-20-multi-item-split-schedule §4.4).
 *
 * 단추 = [data-erp-as-cancel][data-order-id] — 주문 화면 [AS 접수 수정] 창(asReceiveModal) 아래 줄 왼쪽(PC · 휴대폰)과
 * AS 화면 회차 차트 현재 건 머리. 서버가 접수 상태 + 권한(관리자 · CS 능력)일 때만 그린다(as_cancel_allowed).
 *
 * 흐름: 누름 → (창 안이면 창을 닫고) 사유 묻기 → POST /api/orders/<id>/as/cancel {reason} → 그 주문의 접수 초안을
 * 지우고 화면을 다시 읽는다.
 * - 창을 먼저 닫는 까닭: 열린 Bootstrap 창은 포커스를 창 안에 가둬(focus trap) 창 밖 사유 칸에 글을 쓸 수 없다.
 * - 접수 초안(as-receive-draft.js, 열쇠 = 주문 번호 + 창 모드)을 지우는 까닭: 남기면 다음 접수 · 수정 창에
 *   취소한 접수의 옛 글 · 사진이 되살아난다.
 * 사유 창은 새로 만들지 않고 그 화면이 이미 쓰는 것을 쓴다 — 주문 화면은 공용 사유 시트(window.FomsReasonSheet),
 * 그 시트가 없는 AS 화면은 window.prompt(회차 판정과 같은 방식).
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
  var REASON_MAX = 500;
  var DRAFT_CLEAR_WAIT_MS = 1500;

  function orderIdOf(btn) {
    var id = parseInt(btn.getAttribute('data-order-id') || '', 10);
    return id > 0 ? id : 0;
  }

  /**
   * 단추가 열린 Bootstrap 창 안에 있으면 그 창을 닫은 뒤 then 을 부른다(창 밖이면 바로).
   * @param {HTMLElement} btn
   * @param {function(): void} then
   */
  function closeHostModal(btn, then) {
    var modalEl = btn.closest ? btn.closest('.modal') : null;
    var api = window.bootstrap && window.bootstrap.Modal;
    var inst = modalEl && api && typeof api.getInstance === 'function' ? api.getInstance(modalEl) : null;
    if (!modalEl || !inst || !modalEl.classList.contains('show')) {
      then();
      return;
    }
    modalEl.addEventListener('hidden.bs.modal', function () { then(); }, { once: true });
    inst.hide();
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
   * 그 주문의 AS 접수 초안(모든 창 모드)을 지운다. 초안 저장소가 없는 화면이면 아무것도 안 한다.
   * 지우기가 끝나기 전에 화면을 다시 읽으면 초안이 남으므로 끝나기를 잠깐 기다린다.
   * @param {number} orderId
   * @returns {Promise<void>}
   */
  function clearReceiveDraft(orderId) {
    // 초안 열쇠를 비워 두면 뒤늦은 창 닫힘 저장이 옛 글을 다시 넣지 않는다(as-receive-draft.js saveNow).
    window.__erpAsReceiveDraftKey = '';
    var store = window.fomsAsReceiveDraft;
    if (!store || typeof store.clear !== 'function') {
      return Promise.resolve();
    }
    var done;
    try {
      done = Promise.resolve(store.clear(orderId)).catch(function () { return null; });
    } catch (_) {
      return Promise.resolve();
    }
    var timeout = new Promise(function (resolve) { setTimeout(resolve, DRAFT_CLEAR_WAIT_MS); });
    return Promise.race([done, timeout]).then(function () { return undefined; });
  }

  /**
   * 취소 요청을 보낸다. 성공하면 초안을 지우고 화면을 다시 읽고, 실패하면 서버 글을 그대로 보인다.
   * @param {HTMLElement} btn
   * @param {number} orderId
   * @param {string} reason
   */
  async function sendCancel(btn, orderId, reason) {
    if (btn.getAttribute('data-busy') === '1') {
      return;
    }
    if (reason.length > REASON_MAX) {
      window.alert('취소 사유는 ' + REASON_MAX + '자까지 적을 수 있어요.');
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
      await clearReceiveDraft(orderId);
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
    closeHostModal(btn, function () {
      askReason(function (reason) {
        sendCancel(btn, orderId, reason);
      });
    });
  });
})();
