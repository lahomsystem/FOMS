/**
 * 도면 탭 '고객 OK · 확정' 시트(#dwCustomerOkModal) · 바의 [고객 컨펌하고 생산으로].
 * 설계서 docs/specs/2026-09-29-drawing-tab-send-to-customer_SPEC.md §3.5(나·다) · §3.6.
 *
 * - 확정(POST confirm-drawing-receipt) → "컨펌까지"를 골랐고 new_stage === 'CONFIRM' 일 때만 승인(POST quest/approve).
 *   두 요청은 합친 API 가 없어 차례로 부른다. 순서가 곧 안전장치다(확정이 커밋돼야 컨펌 게이트가 열린다, C21).
 * - 어느 경우든 도면 탭에 머문다(/erp/drawing-workbench/<id>?tab=timeline, C14).
 * - 승인 응답 판정: auto_transitioned·next_stage → 생산으로 · all_approved=false → 남은 팀 · 409 ALREADY_TRANSITIONED → 성공.
 * - 관리자 뚫기(FomsAdminOverride)는 붙이지 않는다 — 도면 탭의 확정·컨펌은 정식 경로만.
 * - 수정요청은 출처(고객·영업)를 나누지 않는다(하나의 '수정 요청'). window.fomsDrawingRevisionExtras() 는
 *   빈 객체만 돌려준다 — 인라인 submitRevision 의 typeof 가드가 부르는 자리를 남겨 둔 것.
 */
(function () {
  'use strict';
  if (window.__FOMS_DRAWING_CUSTOMER_OK_BOUND) return;
  window.__FOMS_DRAWING_CUSTOMER_OK_BOUND = true;

  var OK_ID = 'dwCustomerOkModal';
  var busy = false;

  function q(root, sel) { return root ? root.querySelector(sel) : null; }
  function attr(el, name) { return el ? String(el.getAttribute(name) || '') : ''; }
  function checked(root, name) {
    var el = q(root, 'input[name="' + name + '"]:checked');
    return el ? el.value : '';
  }
  function show(el, text) {
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('d-none', !text);
  }
  function notify(message) {
    if (typeof window.fomsShowToast === 'function') window.fomsShowToast(message);
    else window.alert(message);
  }
  function stayUrl(orderId) {
    return '/erp/drawing-workbench/' + encodeURIComponent(orderId) + '?tab=timeline';
  }
  function randomKey() {
    try {
      if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
    } catch (_) { /* 난수 생성 실패는 아래 대체 값으로 */ }
    return 'dwok-' + Date.now() + '-' + Math.random().toString(36).slice(2, 12);
  }

  /** POST JSON — 예외(연결 끊김)는 {thrown: true}. */
  async function postJson(url, body) {
    try {
      var res = await fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(body || {}),
      });
      var data = null;
      try { data = await res.json(); } catch (_) { data = null; }
      return { status: res.status, data: data || {}, thrown: false };
    } catch (_) {
      return { status: 0, data: {}, thrown: true };
    }
  }

  /**
   * 고객 컨펌 승인 — 시트 ②와 바의 [고객 컨펌하고 생산으로]가 같이 쓴다.
   * @returns {Promise<{ok: boolean, text: string}>}
   */
  async function approve(orderId) {
    var res = await postJson('/api/orders/' + encodeURIComponent(orderId) + '/quest/approve',
      { idempotency_key: randomKey() });
    var d = res.data;
    if (res.status === 409 && d.code === 'ALREADY_TRANSITIONED') {
      return { ok: true, text: '이미 생산으로 넘어갔어요' };
    }
    if (!res.thrown && d.success && (d.auto_transitioned || d.next_stage)) {
      return { ok: true, text: '생산으로 넘겼어요' };
    }
    if (!res.thrown && d.success && d.all_approved === false) {
      var teams = Array.isArray(d.missing_teams) ? d.missing_teams.join(', ') : '';
      return { ok: true, text: '승인 기록됨 · 남은 팀: ' + (teams || '-') };
    }
    if (!res.thrown && d.success) return { ok: true, text: '고객 컨펌을 승인했어요' };
    return { ok: false, text: d.message || d.error || (res.thrown ? '네트워크 오류' : ('HTTP ' + res.status)) };
  }

  // ---- 고객 OK 시트 --------------------------------------------------------
  function okMode(root, opener) {
    var mode = attr(opener, 'data-customer-ok-mode') || attr(root, 'data-mode');
    return mode === 'no_customer' ? 'no_customer' : 'customer';
  }

  function refreshOk(root) {
    var approveOn = checked(root, 'dw-ok-after') === 'approve';
    var warn = q(root, '[data-ok-approve-warning]');
    if (warn) warn.classList.toggle('d-none', !approveOn);
    var btn = q(root, '[data-ok-submit]');
    if (btn && !busy) btn.textContent = approveOn ? '확정하고 생산으로 넘기기' : '도면 확정하기';
  }

  function resetOk(root, opener) {
    busy = false;
    var mode = okMode(root, opener);
    root.setAttribute('data-mode', mode);
    var label = attr(root, 'data-round-label');
    var title = q(root, '[data-ok-title]');
    var lead = q(root, '[data-ok-lead]');
    if (title) {
      title.textContent = mode === 'no_customer'
        ? '고객 답 없이 확정할까요?'
        : '고객이 ' + (label ? label + ' ' : '') + '도면으로 OK 했나요?';
    }
    if (lead) {
      lead.textContent = mode === 'no_customer'
        ? '매장에서 직접 OK 받았을 때처럼, 보내기 없이 확정할 수 있어요.'
        : '확정하면 이 도면이 최종본이 돼요.';
    }
    Array.prototype.forEach.call(root.querySelectorAll('input[name="dw-ok-via"]'), function (el) { el.checked = false; });
    var note = q(root, '#dw-ok-note');
    if (note) note.value = '';
    var approveRadio = q(root, '#dw-ok-after-approve');
    if (approveRadio) approveRadio.checked = true;
    var btn = q(root, '[data-ok-submit]');
    if (btn) btn.disabled = false;
    show(q(root, '[data-ok-error]'), '');
    refreshOk(root);
  }

  async function submitOk(root) {
    if (busy) return;
    var orderId = attr(root, 'data-order-id');
    var btn = q(root, '[data-ok-submit]');
    var errEl = q(root, '[data-ok-error]');
    var mode = attr(root, 'data-mode');
    var wantApprove = attr(root, 'data-can-approve') === 'true' && checked(root, 'dw-ok-after') === 'approve';
    busy = true;
    if (btn) btn.disabled = true;
    show(errEl, '');
    var body = {
      customer_ok: mode === 'customer',
      customer_ok_via: checked(root, 'dw-ok-via') || null,
      customer_ok_note: String((q(root, '#dw-ok-note') || {}).value || '').trim().slice(0, 200) || null,
    };
    var res = await postJson('/api/orders/' + encodeURIComponent(orderId) + '/confirm-drawing-receipt', body);
    if (res.thrown || !res.data.success) {
      // ① 실패 — 아무것도 안 바뀌었다. 사유만 보인다.
      show(errEl, '확정하지 못했어요 — ' + (res.data.message || res.data.error || (res.thrown ? '네트워크 오류' : ('HTTP ' + res.status))));
      busy = false;
      if (btn) btn.disabled = false;
      return;
    }
    if (wantApprove && res.data.new_stage === 'CONFIRM') {
      var result = await approve(orderId);
      if (result.ok) {
        notify('도면을 확정했어요 · ' + result.text);
      } else {
        window.alert('도면은 확정했어요. 고객 컨펌은 못 했어요 — ' + result.text
          + '. 도면 탭의 [고객 컨펌하고 생산으로]로 다시 할 수 있어요.');
      }
    } else {
      notify(res.data.message || '도면을 확정했어요');
    }
    window.location.href = stayUrl(orderId);
  }

  async function approveFromBar(btn) {
    if (btn.disabled) return;
    if (!window.confirm('고객 컨펌을 승인하고 생산으로 넘길까요? 생산팀에 알림이 가요.')) return;
    var orderId = attr(btn, 'data-order-id');
    btn.disabled = true;
    var result = await approve(orderId);
    if (!result.ok) {
      window.alert('고객 컨펌을 못 했어요 — ' + result.text);
      btn.disabled = false;
      return;
    }
    notify(result.text);
    window.location.href = stayUrl(orderId);
  }

  /** 인라인 submitRevision 이 본문에 더하는 값. 수정요청은 출처 구분 없이 하나라 늘 빈 객체다(typeof 가드 호환용). */
  window.fomsDrawingRevisionExtras = function () { return {}; };

  document.addEventListener('show.bs.modal', function (e) {
    var root = e.target;
    if (!root) return;
    if (root.id === OK_ID) resetOk(root, e.relatedTarget);
  });
  document.addEventListener('change', function (e) {
    var t = e.target;
    if (!t || !t.name) return;
    if (t.name === 'dw-ok-after') refreshOk(document.getElementById(OK_ID));
  });
  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest ? e.target : null;
    if (!t) return;
    var okBtn = t.closest('[data-ok-submit]');
    if (okBtn) { e.preventDefault(); submitOk(document.getElementById(OK_ID)); return; }
    var approveBtn = t.closest('[data-customer-approve]');
    if (approveBtn) { e.preventDefault(); approveFromBar(approveBtn); }
  });
})();
