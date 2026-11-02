/**
 * "실측 끝 · 도면 넘기기"(영업팀 요청 2026-11-02) — 주문 편집 화면에서 저장 → 도면 단계 → 영발 PUSH 를 한 번에.
 *
 * 전에는 휴대폰에서 실측을 넣고 저장 → PUSH 에서 영발 → 대시보드로 나와 고객을 검색 → "도면 단계로 넘기기"를 눌렀다
 * (운영 10월: 영발 · 넘기기를 같이 한 주문 325건 중 189건이 5분 안에 연달아 눌렀다). 새 API 는 없다 — 이미 있는 세 길을
 * 차례로 부른다:
 *   1. 저장            erpSaveStructured({redirect:false})          (erp-order-shared.js)
 *   2. 도면 단계        POST /api/orders/<id>/quest/approve {}         (대시보드 버튼 drawing-transfer-btn.js 와 같은 길)
 *   3. 영발 PUSH        window.erpRunChannelPush(btn, 'measurement', …) (보낸 적 있으면 바뀐 내용을 먼저 묻는다 — 사용자 결정)
 * 저장이나 넘기기가 실패하면 거기서 멈춘다. 영발이 실패해도 단계는 그대로 두고 "PUSH 로 다시 보내 주세요"를 알린다.
 * 가로 치수가 빈 제품은 막지 않고 확인창에 적는다(사용자 결정 — 사진 · 도면으로 넘기는 경우가 있다).
 * 단추는 서버가 실측 단계 · 승인 권한일 때만 그린다(order_edit_view_context.measure_done_cta).
 */
(function () {
  'use strict';

  /** 제품명은 있는데 가로 치수 칸이 다 빈 제품 이름들(지금 화면 기준). */
  function productsWithoutWidth() {
    var names = [];
    document.querySelectorAll('#erp-items .erp-item-row').forEach(function (row) {
      var nameInput = row.querySelector('[data-erp="product_name"]');
      var name = String((nameInput && nameInput.value) || '').trim();
      if (!name) return;
      var hasWidth = Array.prototype.some.call(row.querySelectorAll('[data-erp="spec_width"]'), function (input) {
        return String(input.value || '').trim() !== '';
      });
      if (!hasWidth) names.push(name);
    });
    return names;
  }

  async function approveToDrawing(orderId) {
    var res = await fetch('/api/orders/' + orderId + '/quest/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    var data;
    try {
      data = await res.json();
    } catch (e) {
      throw new Error(res.redirected || res.status === 401 || res.status === 403
        ? '로그인이 만료되었습니다. 새로고침 후 다시 시도하세요.'
        : '서버 응답을 읽을 수 없습니다 (HTTP ' + res.status + ')');
    }
    if (!data.success) {
      var detail = data.code ? ' (' + data.code + ')' : '';
      throw new Error((data.message || data.error || '도면 단계로 넘기지 못했습니다') + detail);
    }
    if (!data.auto_transitioned) throw new Error('승인은 기록됐지만 단계가 넘어가지 않았습니다. 관리자에게 확인하세요.');
  }

  function goDashboard(orderId) {
    var url = '/erp/dashboard';
    if (typeof window.erpAppendFocusOrderParam === 'function') url = window.erpAppendFocusOrderParam(url, orderId);
    else if (typeof erpAppendFocusOrderParam === 'function') url = erpAppendFocusOrderParam(url, orderId);
    window.location.href = url;
  }

  async function run(btn) {
    var orderId = btn.getAttribute('data-order-id');
    if (!orderId || btn.disabled) return;
    var missing = productsWithoutWidth();
    var text = (btn.getAttribute('data-confirm') || '실측을 완료하고 도면 단계로 넘길까요?')
      + '\n\n저장하고 도면 단계로 넘긴 뒤 영발방에 보냅니다.'
      + (missing.length ? '\n\n가로 치수가 빈 제품: ' + missing.join(', ') : '');
    if (!window.confirm(text)) return;

    // 영발을 보낸 적 있으면 바뀐 내용을 먼저 묻는다 — 취소하면 아무것도 하지 않는다(저장 · 넘기기 전에).
    var changeNote = null;
    if (typeof window.erpHasPriorChannelPush === 'function' && window.erpHasPriorChannelPush('measurement')
        && typeof window.erpPromptChannelPushResendNote === 'function') {
      changeNote = await window.erpPromptChannelPushResendNote('measurement');
      if (!changeNote) return;
    }

    btn.disabled = true;
    var saved = await erpSaveStructured({ redirect: false });
    if (!saved || saved.success !== true) {
      btn.disabled = false;
      return;
    }
    try {
      await approveToDrawing(orderId);
    } catch (err) {
      btn.disabled = false;
      window.alert('저장은 됐지만 도면 단계로 넘기지 못했습니다.\n' + String((err && err.message) || err));
      return;
    }
    var pushed = false;
    if (typeof window.erpRunChannelPush === 'function') {
      // 세 번째 인자가 있으면 저장을 다시 하지 않는다(방금 저장했다). changeNote 가 있으면 재전송.
      pushed = await window.erpRunChannelPush(btn, 'measurement', { resendRecoveryUsed: false, changeNote: changeNote });
    }
    if (!pushed) window.alert('도면 단계로 넘겼습니다. 영발방 전송은 되지 않았으니 PUSH 에서 영발로 다시 보내 주세요.');
    goDashboard(orderId);
  }

  if (!window.__FOMS_ERP_MEASURE_DONE_BOUND) {
    window.__FOMS_ERP_MEASURE_DONE_BOUND = true;
    document.addEventListener('click', function (event) {
      var btn = event.target && event.target.closest ? event.target.closest('[data-erp-measure-done]') : null;
      if (!btn) return;
      event.preventDefault();
      run(btn);
    });
  }
})();
