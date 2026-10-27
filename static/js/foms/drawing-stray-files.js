/**
 * 도면 작업실 '도면 칸에 따로 올라온 파일' 카드(#dw-stray-drawing-card) — 사본 지우기.
 * 설계서 docs/specs/2026-10-27-drawing-team-production-fix_SPEC.md A절(주문 5690).
 *
 * - [지우기] = 기존 DELETE /api/orders/<id>/attachments/<att_id> 그대로(권한·409 는 서버가 정한다).
 * - 결과 문구는 카드 안에 띄운다. 성공하면 그 줄을 지운다. 다 지워도 상자와 문구는 남긴다.
 */
(function () {
  'use strict';
  if (window.__FOMS_DRAWING_STRAY_FILES_BOUND) return;
  window.__FOMS_DRAWING_STRAY_FILES_BOUND = true;

  var CONFIRM_TEXT = '이 파일을 도면 칸에서 지웁니다. 최종 도면은 그대로 남습니다.\n'
    + '잘못 지웠으면 영업이나 관리자가 7일 안에 되살릴 수 있습니다.';

  function setStatus(card, text, ok) {
    var el = card.querySelector('[data-dw-stray-status]');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('d-none', !text);
    el.classList.toggle('text-success', !!ok);
    el.classList.toggle('text-danger', !ok);
  }

  // 다 지워도 상자는 남긴다 — 숨기면 "지웠습니다" 문구까지 사라져 됐는지 모른다(스테이징 실화면).
  function refreshCount(card) {
    var left = card.querySelectorAll('[data-dw-stray-item]').length;
    var countEl = card.querySelector('[data-dw-stray-count]');
    if (countEl) countEl.textContent = String(left);
    var list = card.querySelector('.dw-stray-list');
    if (!left && list) list.classList.add('d-none');
  }

  async function removeOne(card, btn) {
    var item = btn.closest('[data-dw-stray-item]');
    var attId = btn.getAttribute('data-attachment-id') || '';
    var orderId = card.getAttribute('data-order-id') || '';
    if (!item || !attId || !orderId) return;
    if (!window.confirm(CONFIRM_TEXT)) return;
    btn.disabled = true;
    setStatus(card, '', true);
    var data = {};
    try {
      var res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/attachments/' + encodeURIComponent(attId), {
        method: 'DELETE', credentials: 'same-origin', headers: { Accept: 'application/json' },
      });
      try { data = await res.json(); } catch (_) { data = {}; }
    } catch (e) {
      data = { success: false, message: '인터넷 연결을 확인해 주세요.' };
    }
    if (!data || !data.success) {
      btn.disabled = false;
      setStatus(card, (data && data.message) || '지우지 못했습니다. 잠시 뒤 다시 해 주세요.', false);
      return;
    }
    item.remove();
    setStatus(card, '지웠습니다. 최종 도면은 그대로입니다.', true);
    refreshCount(card);
  }

  document.addEventListener('click', function (ev) {
    var btn = ev.target && ev.target.closest ? ev.target.closest('[data-dw-stray-delete]') : null;
    if (!btn) return;
    var card = btn.closest('#dw-stray-drawing-card');
    if (!card) return;
    ev.preventDefault();
    removeOne(card, btn);
  });
})();
