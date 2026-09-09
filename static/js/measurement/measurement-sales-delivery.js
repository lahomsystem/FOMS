/**
 * 실측 대시보드 · 동행 전달 카드의 [전달 완료] 버튼.
 *
 * 스펙: docs/specs/2026-09-09-as-sales-delivery-measurement-assignment-design.md §6.2·§7
 * POST /api/orders/<id>/sales-delivery  body {"action":"deliver"}
 *
 * - CSRF 는 전역 인터셉터(templates/partials/shared/csrf_bootstrap.html)가 붙인다. 수동 부착 금지.
 * - 실패를 .alert 로만 알리지 않는다(5초 자동 닫힘 = 무음 실패). 버튼 옆 인라인 텍스트 병행.
 * - 이 파일은 fragment(dashboard_scripts.html) 안에서 탭 스왑마다 재실행될 수 있으므로
 *   document 위임 1회 등록 + singleton 가드로 리스너 누적을 막는다(재초기화 불필요).
 */
(function () {
  if (window.__fomsMeasurementSalesDeliveryBound) return;
  window.__fomsMeasurementSalesDeliveryBound = true;

  function setMessage(card, text, isError) {
    if (!card) return;
    var slot = card.querySelector('[data-meas-sd-msg]');
    if (!slot) return;
    slot.textContent = text || '';
    slot.classList.toggle('is-error', !!isError);
  }

  function markDelivered(card, button) {
    var done = document.createElement('span');
    done.className = 'meas-sd-done';
    done.setAttribute('data-meas-sd-done', '');
    done.textContent = '전달 완료됨';
    if (button && button.parentNode) {
      button.parentNode.replaceChild(done, button);
    }
    if (!card) return;
    var state = card.querySelector('.meas-sd-state');
    if (state) {
      state.classList.remove('meas-sd-state--assigned');
      state.classList.add('meas-sd-state--delivered');
      state.textContent = '전달완료';
    }
    setMessage(card, '', false);
  }

  async function deliver(button) {
    var card = button.closest ? button.closest('.meas-sd-card') : null;
    var orderId = button.getAttribute('data-meas-sd-deliver');
    if (!orderId || button.disabled) return;
    button.disabled = true;
    setMessage(card, '전달 완료 처리 중...', false);

    try {
      var res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/sales-delivery', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'deliver' })
      });
      var data = null;
      try {
        data = await res.json();
      } catch (parseErr) {
        data = null;
      }
      if (!res.ok || !data || data.success !== true) {
        throw new Error(
          (data && (data.message || data.error)) || ('요청 실패 (HTTP ' + res.status + ')')
        );
      }
      markDelivered(card, button);
    } catch (err) {
      button.disabled = false;
      setMessage(card, '전달 완료 실패: ' + ((err && err.message) || '알 수 없는 오류'), true);
    }
  }

  document.addEventListener('click', function (evt) {
    var target = evt.target;
    if (!target || !target.closest) return;
    var button = target.closest('[data-meas-sd-deliver]');
    if (!button) return;
    evt.preventDefault();
    deliver(button);
  });
})();
