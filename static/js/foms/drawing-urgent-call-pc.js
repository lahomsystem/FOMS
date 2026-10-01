/**
 * 도면 작업실 PC 긴급 호출 창(#dwUrgentCallModal) + 전달 취소 경고 시트(#dwCancelWarnModal) — 사용자 결정 Q5-①④.
 *
 * - 모바일 긴급 호출 시트(urgent-call-sheet.js, [data-foms-urgent-call])는 모바일 셸(d-lg-none) 안이라 PC 에서 안 뜬다.
 *   PC 는 [data-dw-urgent-call] 로 이 창을 열고, 엔드포인트는 모바일 시트와 같다:
 *   GET /erp/api/orders/<id>/urgent-targets · POST /erp/api/orders/<id>/urgent-mention(FOMSNotificationWrite).
 * - 전달 취소 경고 시트의 '영업에게 먼저 알리기': 시트를 닫은 뒤, 모바일 셸이 보이는 폭이면 기존 모바일 시트를
 *   (숨은 [data-foms-urgent-call] 버튼으로) 열고, 아니면 이 PC 창을 연다. data-urgent-team 팀을 펼치고
 *   data-urgent-message 로 사유를 미리 채운다.
 * - [그래도 취소]는 전달 취소 API 를 곧바로 부른다(확인창을 두 번 띄우지 않는다).
 * - window.fomsDrawingCancelWarn(btn): 경고 시트 열기(폭별 문구 고르기). 인라인 cancelTransfer 가 이 JS 가 떴을 때만
 *   부르고, 안 떴으면 경고 문구 확인창으로 간다(시트만 열리고 [그래도 취소]가 죽는 일이 없게).
 * - 사람 이름은 textContent 로만 넣고, id 는 정수만 받는다.
 * - 사람 버튼은 .foms-urgent-pick(+ .is-selected) — 전역 style-pro-max.css 의 .btn-outline-secondary
 *   (background !important)가 Bootstrap .active 를 덮어 눌러도 표시가 안 나던 결함(2026-10-01)을 피한다.
 *   고른 사람은 [data-dw-urgent-picked] 줄에, 보내기가 잠긴 이유는 [data-dw-urgent-hint] 에 글로 보여 준다.
 */
(function () {
  'use strict';
  if (window.__FOMS_DRAWING_URGENT_PC_BOUND) return;
  window.__FOMS_DRAWING_URGENT_PC_BOUND = true;

  var MODAL_ID = 'dwUrgentCallModal';
  var WARN_ID = 'dwCancelWarnModal';
  var MAX_MESSAGE = 500;
  var current = { orderId: '', targetId: null, targetName: '', team: '', loading: false };

  function q(root, sel) { return root ? root.querySelector(sel) : null; }
  function attr(el, name) { return el ? String(el.getAttribute(name) || '') : ''; }
  function show(el, text) {
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('d-none', !text);
  }
  function modalApi() { return window.bootstrap && window.bootstrap.Modal ? window.bootstrap.Modal : null; }
  function notify(message) {
    if (typeof window.fomsShowToast === 'function') window.fomsShowToast(message);
    else window.alert(message);
  }

  function syncSend(root) {
    var btn = q(root, '[data-dw-urgent-send]');
    var msg = String((q(root, '#dw-urgent-message') || {}).value || '').trim();
    if (btn) btn.disabled = !(current.targetId !== null && msg);
    var picked = q(root, '[data-dw-urgent-picked]');
    show(picked, current.targetId !== null ? '받는 사람: ' + current.targetName : '');
    var hint = q(root, '[data-dw-urgent-hint]');
    if (hint) {
      hint.textContent = current.targetId === null ? '받을 사람을 먼저 눌러 주세요.'
        : (msg ? '' : '사유를 적으면 보낼 수 있어요.');
    }
  }

  function renderTargets(root, targets) {
    var box = q(root, '[data-dw-urgent-targets]');
    if (!box) return;
    box.textContent = '';
    var groups = [];
    var byTeam = {};
    (Array.isArray(targets) ? targets : []).forEach(function (u) {
      if (!u || !Number.isInteger(Number(u.id))) return;
      var key = String(u.team_label || '기타');
      if (!byTeam[key]) { byTeam[key] = { label: key, team: String(u.team || ''), members: [] }; groups.push(byTeam[key]); }
      byTeam[key].members.push(u);
    });
    if (!groups.length) {
      box.textContent = '호출할 담당자가 없습니다.';
      return;
    }
    groups.forEach(function (g) {
      var det = document.createElement('details');
      det.className = 'mb-1';
      if (groups.length <= 1 || (current.team && g.team === current.team)) det.open = true;
      var sum = document.createElement('summary');
      sum.className = 'small fw-semibold';
      sum.textContent = g.label + ' ' + g.members.length;
      det.appendChild(sum);
      var row = document.createElement('div');
      row.className = 'd-flex flex-wrap gap-1 py-1';
      g.members.forEach(function (u) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'btn btn-sm foms-urgent-pick';
        b.setAttribute('data-dw-urgent-target', String(Number(u.id)));
        b.setAttribute('data-target-name', String(u.name || '').trim());
        b.setAttribute('aria-pressed', 'false');
        b.textContent = String(u.name || '').trim() + (u.role ? ' · ' + String(u.role) : '');
        row.appendChild(b);
      });
      det.appendChild(row);
      box.appendChild(det);
    });
  }

  async function loadTargets(root) {
    var box = q(root, '[data-dw-urgent-targets]');
    if (!box || current.loading) return;
    current.loading = true;
    box.textContent = '대상 불러오는 중...';
    try {
      var res = await fetch('/erp/api/orders/' + encodeURIComponent(current.orderId) + '/urgent-targets', {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
      });
      var data = await res.json();
      if (!res.ok || !data || !data.success) throw new Error((data && data.message) || ('HTTP ' + res.status));
      renderTargets(root, data.targets || []);
    } catch (err) {
      box.textContent = '호출 대상을 불러오지 못했습니다.';
    } finally {
      current.loading = false;
    }
  }

  function selectTarget(root, btn) {
    current.targetId = Number(btn.getAttribute('data-dw-urgent-target'));
    if (!Number.isInteger(current.targetId)) current.targetId = null;
    current.targetName = current.targetId === null ? '' : attr(btn, 'data-target-name');
    Array.prototype.forEach.call(root.querySelectorAll('[data-dw-urgent-target]'), function (el) {
      var on = el === btn;
      el.classList.toggle('is-selected', on);
      el.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    syncSend(root);
  }

  async function send(root) {
    var btn = q(root, '[data-dw-urgent-send]');
    if (!btn || btn.disabled || current.targetId === null) return;
    var message = String((q(root, '#dw-urgent-message') || {}).value || '').trim().slice(0, MAX_MESSAGE);
    var errEl = q(root, '[data-dw-urgent-error]');
    if (!window.FOMSNotificationWrite || typeof window.FOMSNotificationWrite.fetch !== 'function') {
      show(errEl, '긴급 호출을 보낼 수 없습니다. 화면을 새로고침해 주세요.');
      return;
    }
    btn.disabled = true;
    show(errEl, '');
    try {
      var res = await window.FOMSNotificationWrite.fetch(
        '/erp/api/orders/' + encodeURIComponent(current.orderId) + '/urgent-mention',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ target_user_id: current.targetId, message: message }),
        }
      );
      var data = await res.json();
      if (!data || !data.success) throw new Error((data && data.message) || '긴급 호출 발송 실패');
      var api = modalApi();
      if (api) api.getOrCreateInstance(root).hide();
      notify(data.message || '긴급 호출을 보냈습니다.');
    } catch (err) {
      show(errEl, (err && err.message) || '긴급 호출 발송에 실패했습니다.');
      syncSend(root);
    }
  }

  function openPc(opener) {
    var root = document.getElementById(MODAL_ID);
    var api = modalApi();
    if (!root || !api) return;
    current.orderId = attr(opener, 'data-order-id') || attr(root, 'data-order-id');
    current.team = attr(opener, 'data-urgent-team');
    current.targetId = null;
    current.targetName = '';
    var msg = q(root, '#dw-urgent-message');
    if (msg) msg.value = attr(opener, 'data-urgent-message').slice(0, MAX_MESSAGE);
    show(q(root, '[data-dw-urgent-error]'), '');
    syncSend(root);
    api.getOrCreateInstance(root).show();
    loadTargets(root);
  }

  /** 모바일 셸이 보이면 기존 모바일 시트, 아니면 PC 창. */
  function openFor(opener) {
    var shell = document.querySelector('.foms-drawing-handoff');
    var proxy = document.querySelector('[data-cancel-warn-mobile-proxy]');
    var sheet = document.getElementById('erp-mobile-urgent-call-sheet');
    if (shell && shell.getClientRects().length > 0 && proxy && sheet) {
      proxy.click(); // urgent-call-sheet.js 의 document 위임 처리가 시트를 연다
      var mobileMsg = document.querySelector('[data-foms-urgent-message]');
      if (mobileMsg) mobileMsg.value = attr(opener, 'data-urgent-message').slice(0, MAX_MESSAGE);
      return;
    }
    openPc(opener);
  }

  function handleOpener(opener) {
    var api = modalApi();
    var openModal = opener.closest('.modal.show');
    if (openModal && api) {
      // 열린 시트(전달 취소 경고) 위에 창을 겹치지 않는다 — 닫힌 뒤 연다.
      openModal.addEventListener('hidden.bs.modal', function () { openFor(opener); }, { once: true });
      api.getOrCreateInstance(openModal).hide();
      return;
    }
    openFor(opener);
  }

  /**
   * 인라인 cancelTransfer 가 부른다: 보낸 회차면(서버가 싣는 폭별 문구가 있으면) 경고 시트를 열고 true.
   * 문구가 없거나 시트·Bootstrap 이 없으면 false — 부르는 쪽이 기존 확인창 경로로 간다.
   * @param {Element|null} cancelBtn #btn-cancel-transfer
   * @returns {boolean}
   */
  function openCancelWarn(cancelBtn) {
    var narrow = !!(window.matchMedia && window.matchMedia('(max-width: 991.98px)').matches);
    var text = attr(cancelBtn, narrow ? 'data-customer-sent-text-mobile' : 'data-customer-sent-text-pc')
      || attr(cancelBtn, 'data-customer-sent-text-pc') || attr(cancelBtn, 'data-customer-sent-text-mobile');
    var root = document.getElementById(WARN_ID);
    var api = modalApi();
    if (!text || !root || !api) return false;
    var textEl = q(root, '[data-cancel-warn-text]');
    if (textEl) textEl.textContent = text;
    show(q(root, '[data-cancel-warn-error]'), '');
    api.getOrCreateInstance(root).show();
    return true;
  }
  window.fomsDrawingCancelWarn = openCancelWarn;

  /** 전달 취소 경고 시트의 [그래도 취소]. */
  async function confirmCancelTransfer(btn) {
    if (btn.disabled) return;
    var root = document.getElementById(WARN_ID);
    var orderId = attr(root, 'data-order-id');
    var errEl = q(root, '[data-cancel-warn-error]');
    btn.disabled = true;
    show(errEl, '');
    try {
      var res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/cancel-transfer', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      var data = await res.json();
      if (!data || !data.success) {
        show(errEl, (data && data.message) || '전달 취소에 실패했어요');
        btn.disabled = false;
        return;
      }
      window.location.href = '/erp/drawing-workbench/' + encodeURIComponent(orderId) + '?tab=timeline';
    } catch (_) {
      show(errEl, '전달 취소 중 오류가 났어요. 잠시 뒤 다시 눌러 주세요.');
      btn.disabled = false;
    }
  }

  document.addEventListener('input', function (e) {
    if (e.target && e.target.id === 'dw-urgent-message') syncSend(document.getElementById(MODAL_ID));
  });
  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest ? e.target : null;
    if (!t) return;
    var opener = t.closest('[data-dw-urgent-call]');
    if (opener) { e.preventDefault(); handleOpener(opener); return; }
    var root = document.getElementById(MODAL_ID);
    var target = t.closest('[data-dw-urgent-target]');
    if (target && root && root.contains(target)) { e.preventDefault(); selectTarget(root, target); return; }
    if (t.closest('[data-dw-urgent-send]') && root) { e.preventDefault(); send(root); return; }
    var cancelBtn = t.closest('[data-cancel-transfer-confirm]');
    if (cancelBtn) { e.preventDefault(); confirmCancelTransfer(cancelBtn); }
  });
})();
