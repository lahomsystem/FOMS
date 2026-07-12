/**
 * B3 생산 공정 스텝 토글 (모바일 v2 생산 큐 카드).
 *
 * 위임 클릭 → POST /api/orders/<id>/production/steps {key, done} → 행/배지 갱신.
 * ERP shell fragment 재실행 대비 window.__FOMS_PROD_STEPS_BOUND 싱글톤 가드로
 * 전역 listener 중복 바인딩을 차단한다(perf 가드 G4).
 */
(function () {
  'use strict';
  if (window.__FOMS_PROD_STEPS_BOUND) return;
  window.__FOMS_PROD_STEPS_BOUND = true;

  function formatAt(iso) {
    if (!iso) return '';
    // UTC iso 를 로컬 표시(YYYY-MM-DD HH:MM)로. 파싱 실패 시 앞 16자 폴백.
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso).slice(0, 16).replace('T', ' ');
    var pad = function (n) { return String(n).padStart(2, '0'); };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
      ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  function applyStepState(container, step) {
    if (!container || !step) return;
    var row = container.querySelector('[data-foms-prod-step-row][data-step-key="' + step.key + '"]');
    if (!row) return;
    var btn = row.querySelector('[data-foms-prod-step-toggle]');
    var meta = row.querySelector('[data-foms-prod-step-meta]');
    var done = !!step.done;
    row.classList.toggle('is-done', done);
    if (btn) btn.setAttribute('aria-pressed', done ? 'true' : 'false');
    if (meta) {
      if (done) {
        var at = formatAt(step.at);
        meta.textContent = step.by_name ? (at + ' · ' + step.by_name) : at;
      } else {
        meta.textContent = '';
      }
    }
  }

  function updateBadge(container, doneCount, total) {
    if (!container) return;
    var badge = container.querySelector('[data-foms-prod-steps-badge]');
    if (badge) badge.textContent = '공정 ' + doneCount + '/' + (total || 5);
  }

  async function toggleStep(btn) {
    var orderId = btn.getAttribute('data-order-id');
    var key = btn.getAttribute('data-step-key');
    if (!orderId || !key) return;
    var container = btn.closest('[data-foms-prod-steps]');
    var nextDone = btn.getAttribute('aria-pressed') !== 'true';
    if (btn.disabled) return;
    btn.disabled = true;
    try {
      var res = await fetch('/api/orders/' + orderId + '/production/steps', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: key, done: nextDone })
      });
      var data = await res.json();
      if (!res.ok || !data.success) {
        alert('공정 저장 실패: ' + (data && (data.error || data.message) || ('HTTP ' + res.status)));
        return;
      }
      var payload = data.data || {};
      var steps = payload.steps || [];
      steps.forEach(function (s) { applyStepState(container, s); });
      updateBadge(container, payload.done_count || 0, payload.total || steps.length);
    } catch (err) {
      console.error('production step toggle error:', err);
      alert('공정 저장 중 오류가 발생했습니다.');
    } finally {
      btn.disabled = false;
    }
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-foms-prod-step-toggle]');
    if (!btn) return;
    e.preventDefault();
    toggleStep(btn);
  });
})();
