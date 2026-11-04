/**
 * 협력사 주문 지우기(templates/partner/partials/order_delete.html, 설계서 2026-11-04-partner-order-delete).
 * "이 주문 지우기" → 이유 칸 펼침 → "지우기" = POST data-url {reason} → 주문 목록으로. 글은 textContent 로만 넣는다.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-pp-delete]');
  if (!root) return;
  var form = root.querySelector('[data-pp-delete-form]');
  var input = root.querySelector('#ppDeleteReason');
  var go = root.querySelector('[data-pp-delete-go]');

  function status(text) { root.querySelector('[data-pp-delete-status]').textContent = text || ''; }

  root.querySelector('[data-pp-delete-open]').addEventListener('click', function () {
    form.hidden = false;
    input.focus();
  });
  root.querySelector('[data-pp-delete-cancel]').addEventListener('click', function () {
    form.hidden = true;
    input.value = '';
    status('');
  });

  go.addEventListener('click', async function () {
    var reason = input.value.trim();
    if (!reason) { status('지우는 이유를 한 줄 적어 주세요.'); input.focus(); return; }
    go.disabled = true;
    var res = null;
    try {
      res = await fetch(root.getAttribute('data-url'), { method: 'POST', credentials: 'same-origin',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: JSON.stringify({ reason: reason }) });
      res = await res.json();
    } catch (_) {
      res = null;
    }
    if (!res || !res.success) {
      go.disabled = false;
      status((res && res.error) || '지우지 못했습니다. 인터넷 연결을 확인하고 다시 시도해 주세요.');
      return;
    }
    status('지웠습니다. 목록으로 갑니다.');
    window.location.href = (res.data && res.data.redirect) || '/partner';
  });
})();
