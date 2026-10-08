/**
 * 도면 탭 '고객에게 보내기' 시트(#dwCustomerSendModal) — 전달 취소 경고 시트는 drawing-urgent-call-pc.js.
 * 설계서 docs/specs/2026-09-29-drawing-tab-send-to-customer_SPEC.md §3.5(가) · §3.6 · 사용자 결정 Q5-②.
 *
 * - 서버는 기존 /api/share/* 를 그대로 부른다(create → send-alimtalk | send-sms, 내 폰 문자는 sms: 딥링크).
 * - 버튼은 응답이 올 때까지 잠근다. 도면 탭은 누를 때마다 새 링크라 서버 5초 중복 막기가 안 걸린다(§2.1).
 * - 발송 전 단계 실패(400·404·409·410·503)면 방금 만든 링크를 곧바로 회수한다(고아 링크가 '링크만 만듦'으로 안 보이게).
 * - 'network'·'unknown'·연결 끊김은 실제로 나갔을 수 있다 → 회수하지 않고 버튼을 잠근 채 둔다(두 통 방지).
 * - 토큰 원문은 이 함수 안 변수에만 둔다(저장소에 쓰지 않는다).
 * - window.FomsCustomerSend.savePhone(orderId, phone): '주문 고객 번호도 저장'(Q5-②) — 기존 인라인 라우트
 *   PATCH /api/orders/<id>/structured/fields(parties.customer.phone), 하이픈 형식, X-If-Match=structured_updated_at.
 */
(function () {
  'use strict';
  if (window.__FOMS_DRAWING_CUSTOMER_SEND_BOUND) return;
  window.__FOMS_DRAWING_CUSTOMER_SEND_BOUND = true;

  var MODAL_ID = 'dwCustomerSendModal';
  var PRE_SEND_FAIL = [400, 401, 403, 404, 409, 410, 503];
  // erp-share.js ERROR_LABELS 와 같은 코드 → 같은 문구(서버 코드가 정본).
  var ERROR_LABELS = {
    order_not_found: '주문을 찾을 수 없습니다',
    partner_order: '협력사 주문 — 고객 연락은 협력사가 합니다',
    unknown_kind: '알 수 없는 공유 종류입니다',
    share_not_found: '공유 링크를 찾을 수 없습니다',
    token_mismatch: '링크 정보가 맞지 않습니다 — 회수 후 다시 발급해 주세요',
    share_expired: '만료된 링크입니다 — 다시 발급해 주세요',
    share_revoked: '회수된 링크입니다 — 다시 발급해 주세요',
    no_valid_phone: '고객 휴대폰 번호가 올바르지 않습니다',
    not_configured: '문자 발신 설정이 없습니다 — 관리자에게 문의하세요',
    duplicate_send: '방금 발송을 시도했습니다 — 잠시 후 다시 시도해 주세요',
    invalid_phone: '수신 번호가 올바르지 않습니다', INVALID_PHONE: '수신 번호가 올바르지 않습니다',
    template_mismatch: '승인된 템플릿과 본문이 일치하지 않습니다', length_exceeded: '본문이 1,000자를 넘었습니다',
    unknown: '보냈는지 확인되지 않는 오류가 났습니다',
    snapshot_too_large: '보낼 내용이 너무 큽니다',
    auth: '문자 인증 정보가 올바르지 않습니다',
    balance: '문자 잔액이 부족합니다',
    network: '네트워크 오류가 발생했습니다',
  };
  var CHANNEL_LABELS = { kakao: '알림톡', company: '회사 문자', mine: '내 문자 앱' };
  var SUBMIT_LABELS = { kakao: '알림톡 보내기', company: '회사 문자 보내기', mine: '내 문자 앱 열기' };

  var state = { busy: false, locked: false, reloadOnHide: false };

  function label(code) { return ERROR_LABELS[code] || String(code || '알 수 없는 오류'); }
  function modal() { return document.getElementById(MODAL_ID); }
  function q(root, sel) { return root ? root.querySelector(sel) : null; }
  function attr(el, name) { return el ? String(el.getAttribute(name) || '') : ''; }
  function checked(root, name) {
    var el = q(root, 'input[name="' + name + '"]:checked');
    return el ? el.value : '';
  }
  function show(el, text) {
    if (!el) return;
    if (typeof text === 'string') el.textContent = text;
    el.classList.toggle('d-none', !text);
  }

  /** 입력 번호를 숫자만 남긴다. 휴대폰 모양(01X, 10~11자리)이 아니면 ''. 최종 판정은 서버. */
  function normalizePhone(raw) {
    var digits = String(raw || '').replace(/[^0-9]/g, '');
    return /^01[016789][0-9]{7,8}$/.test(digits) ? digits : '';
  }
  function hyphenPhone(d) { var m = d.length - 4; return d.slice(0, 3) + '-' + d.slice(3, m) + '-' + d.slice(m); }

  function overridePhone(root) {
    var box = q(root, '[data-send-phone-edit]');
    if (!box || box.classList.contains('d-none')) return { raw: '', phone: '' };
    var raw = String((q(root, '#dw-send-phone') || {}).value || '').trim();
    return { raw: raw, phone: normalizePhone(raw) };
  }

  function lockButtons(root, on) {
    var btn = q(root, '[data-send-submit]');
    if (btn) btn.disabled = !!on;
    Array.prototype.forEach.call(root.querySelectorAll('input[name="dw-send-kind"], input[name="dw-send-channel"]'), function (el) {
      el.disabled = !!on;
    });
  }

  /** 고객이 받는 모습(문서 이름만 — 템플릿 원문은 베끼지 않는다, §3.5 가). */
  function refresh(root) {
    var kind = checked(root, 'dw-send-kind') || 'drawing';
    var channel = checked(root, 'dw-send-channel') || 'kakao';
    var preview = q(root, '[data-send-preview]');
    var text;
    if (kind === 'bundle' && channel === 'kakao' && attr(root, 'data-bundle-both-template') === 'true') {
      text = '버튼 2개(도면 · 계약서) 알림톡으로 가요. 문서 이름은 템플릿에 고정돼 회차가 안 들어가요.';
    } else if (kind === 'bundle') {
      text = '문서 이름: ' + attr(root, 'data-doc-label-bundle');
    } else {
      text = '문서 이름: ' + attr(root, 'data-doc-label-drawing');
    }
    if (preview) preview.textContent = text;
    var btn = q(root, '[data-send-submit]');
    if (btn) btn.textContent = SUBMIT_LABELS[channel] || SUBMIT_LABELS.kakao;
    var ov = overridePhone(root);
    var hasPhone = attr(root, 'data-has-phone') === 'true' || !!ov.phone;
    var needPhone = channel !== 'mine';
    show(q(root, '[data-send-nophone]'), needPhone && !hasPhone ? '고객 휴대폰 번호가 없어요' : '');
    if (btn && !state.locked && !state.busy) btn.disabled = needPhone && !hasPhone;
  }

  function resetSheet(root, mode) {
    state.busy = false;
    state.locked = false;
    state.reloadOnHide = false;
    var drawing = q(root, '#dw-send-kind-drawing');
    var kakao = q(root, '#dw-send-channel-kakao');
    if (drawing) drawing.checked = true;
    if (kakao) kakao.checked = true;
    lockButtons(root, false);
    var again = q(root, '[data-send-again]');
    var againText = q(root, '[data-send-again-text]');
    if (againText) againText.textContent = attr(root, 'data-sent-text');
    if (again) again.classList.toggle('d-none', mode !== 'again');
    show(q(root, '[data-send-error]'), '');
    show(q(root, '[data-send-status]'), '');
    refresh(root);
  }

  /** POST JSON — 예외(연결 끊김)는 {thrown: true} 로 돌려준다(호출 쪽이 '결과 모름'으로 다룬다). */
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
      return { status: res.status, data: data, thrown: false };
    } catch (_) {
      return { status: 0, data: null, thrown: true };
    }
  }

  /** 방금 만든 링크 회수 — 실패해도 무시(멱등, 화면 흐름을 막지 않는다). */
  async function revokeShare(shareId) {
    if (!shareId) return;
    try {
      await fetch('/api/share/revoke/' + encodeURIComponent(shareId), { method: 'POST', credentials: 'same-origin' });
    } catch (_) { /* 회수 실패는 무시 — 발급 이력 창에서 다시 회수할 수 있다 */ }
  }

  function smsHref(phone, text) {
    var sep = /iPad|iPhone|iPod|Macintosh/.test(navigator.userAgent) ? '&' : '?';
    return 'sms:' + phone + sep + 'body=' + encodeURIComponent(text);
  }

  /**
   * 주문 고객 번호 저장(Q5-② '주문 고객 번호도 저장') — 기존 인라인 필드 수정 라우트.
   * @returns {Promise<{ok: boolean, error: string}>}
   */
  async function savePhone(orderId, phone) {
    var digits = normalizePhone(phone);
    var headers = { 'Content-Type': 'application/json', Accept: 'application/json' };
    var stamp = attr(modal(), 'data-structured-updated-at');
    if (stamp) headers['X-If-Match'] = stamp; // 그새 주문이 바뀌었으면 서버가 409 CONFLICT
    try {
      var res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/structured/fields', {
        method: 'PATCH', credentials: 'same-origin', headers: headers,
        body: JSON.stringify({ field: 'parties.customer.phone', value: digits ? hyphenPhone(digits) : String(phone || '') }),
      });
      var data = await res.json();
      if (res.ok && data && data.success) return { ok: true, error: '' };
      if (data && data.error === 'CONFLICT') return { ok: false, error: '주문이 다른 곳에서 먼저 바뀌었어요 — 주문 화면에서 고쳐 주세요' };
      if (data && data.error === 'INLINE_DISABLED') return { ok: false, error: '주문 번호 저장은 주문 화면에서 해 주세요' };
      return { ok: false, error: (data && (data.message || data.error)) || ('HTTP ' + res.status) };
    } catch (_) {
      return { ok: false, error: label('network') };
    }
  }
  window.FomsCustomerSend = { savePhone: savePhone };

  async function finishSaved(root, orderId, phone, doneText) {
    var statusEl = q(root, '[data-send-status]');
    if (!phone || !(q(root, '#dw-send-save-phone') || {}).checked) return true;
    var saved = await savePhone(orderId, phone);
    if (saved.ok) return true;
    show(statusEl, doneText + ' 주문 번호 저장은 못 했어요 — ' + saved.error);
    state.reloadOnHide = true;
    return false;
  }

  var UNSURE = '보냈는지 확실하지 않아요 — 잠시 뒤 새로고침해 상태 줄을 확인하세요';

  /** 결과 줄 + 버튼 상태. hold=true 면 잠근 채 둔다(나갔을 수 있음 — 바로 재시도 금지, 닫으면 새로고침). */
  function settle(root, errText, hold) {
    show(q(root, '[data-send-error]'), errText);
    if (hold) { state.locked = true; state.reloadOnHide = true; return; }
    state.busy = false;
    lockButtons(root, false);
    refresh(root);
  }

  async function submit(root) {
    if (state.busy || state.locked) return;
    var orderId = attr(root, 'data-order-id');
    var kind = checked(root, 'dw-send-kind') || 'drawing';
    var channel = checked(root, 'dw-send-channel') || 'kakao';
    var ov = overridePhone(root);
    if (ov.raw && !ov.phone) { show(q(root, '[data-send-error]'), label('invalid_phone')); return; }
    state.busy = true;
    lockButtons(root, true);
    show(q(root, '[data-send-error]'), '');
    var created = await postJson('/api/share/create/' + encodeURIComponent(orderId), { kind: kind });
    // 만들기 요청이 끊김 — 서버엔 링크가 생겼을 수 있다. 바로 다시 누르면 링크가 둘 → 잠그고 닫으면 새로고침.
    if (created.thrown) { settle(root, '링크를 만들었는지 확실하지 않아요 — 닫으면 새로고침해 상태 줄을 확인해요', true); return; }
    var data = created.data;
    if (!data || !data.success || !data.data) {
      settle(root, '링크를 만들지 못했어요 — ' + label((data && data.error) || 'network'), false);
      return;
    }
    var shareId = data.data.share_id;
    var token = data.data.token;
    var roundLabel = attr(root, 'data-round-label');
    var customerName = attr(root, 'data-customer-name');
    var doneText = (customerName ? customerName + ' ' : '') + '고객님께 ' + (roundLabel ? roundLabel + ' ' : '') + '도면을 보냈어요.';

    if (channel === 'mine') {
      var to = ov.phone || data.data.to_phone || '';
      if (!to) { await revokeShare(shareId); settle(root, label('no_valid_phone'), false); return; }
      state.locked = true;
      state.reloadOnHide = true;
      show(q(root, '[data-send-status]'), '문자 앱을 열었어요. 링크를 만들었어요(직접 보낸 경우 보냈는지는 기록되지 않아요).');
      await finishSaved(root, orderId, ov.phone, '문자 앱을 열었어요.');
      window.location.href = smsHref(to, data.data.sms_text || data.data.url);
      return;
    }

    var url = (channel === 'company' ? '/api/share/send-sms/' : '/api/share/send-alimtalk/') + encodeURIComponent(shareId);
    var body = { token: token, source_screen: 'drawing_tab' };
    if (ov.phone) body.to_phone = ov.phone;
    var sent = await postJson(url, body);
    token = null;
    body = null;
    // 연결 끊김 — 나갔는지 모른다. 회수 금지 · 버튼 잠금 유지(바로 재시도하면 두 통).
    if (sent.thrown) { settle(root, UNSURE, true); return; }
    var sd = sent.data || {};
    var result = sd.data || {};
    if (sent.status === 200 && result.sent === true) {
      state.locked = true;
      if (!(await finishSaved(root, orderId, ov.phone, doneText))) return;
      show(q(root, '[data-send-status]'), doneText);
      window.location.reload();
      return;
    }
    if (PRE_SEND_FAIL.indexOf(sent.status) !== -1) {
      // 발송 전 단계 실패 — 이벤트가 없거나 롤백됐다. 방금 만든 링크를 회수한다.
      await revokeShare(shareId);
      settle(root, CHANNEL_LABELS[channel] + '을 보내지 못했어요 — ' + label(sd.error || result.error), false);
      return;
    }
    var code = result.error || sd.error || '';
    if (sent.status === 200 && code && code !== 'network' && code !== 'unknown') {
      // 벤더가 접수를 거절 — 고객에게 안 갔다. 이벤트가 실패로 남으므로 회수하지 않는다.
      state.reloadOnHide = true;
      settle(root, CHANNEL_LABELS[channel] + '이 접수되지 않았어요 — ' + label(code), false);
      return;
    }
    // 'network'·'unknown'(분류 못 한 예외) 또는 알 수 없는 응답 — 실제로 나갔을 수 있다. 회수 금지 · 잠금 유지.
    settle(root, UNSURE, true);
  }

  document.addEventListener('show.bs.modal', function (e) {
    var root = e.target;
    if (!root || root.id !== MODAL_ID) return;
    var opener = e.relatedTarget;
    resetSheet(root, attr(opener, 'data-customer-send-mode') === 'again' ? 'again' : 'first');
  });
  document.addEventListener('hidden.bs.modal', function (e) {
    if (e.target && e.target.id === MODAL_ID && state.reloadOnHide) window.location.reload();
  });
  document.addEventListener('change', function (e) {
    var root = modal();
    if (root && e.target && root.contains(e.target)) refresh(root);
  });
  document.addEventListener('input', function (e) {
    var root = modal();
    if (root && e.target && e.target.id === 'dw-send-phone') refresh(root);
  });
  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest ? e.target : null;
    if (!t) return;
    var root = modal();
    var toggle = t.closest('[data-send-phone-toggle]');
    if (toggle && root) {
      var box = q(root, '[data-send-phone-edit]');
      if (box) box.classList.toggle('d-none');
      toggle.setAttribute('aria-expanded', box && !box.classList.contains('d-none') ? 'true' : 'false');
      refresh(root);
      return;
    }
    if (t.closest('[data-send-submit]') && root) { e.preventDefault(); submit(root); }
  });
})();
