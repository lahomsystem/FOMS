/**
 * Mobile urgent-call sheet — Phase 2.
 *
 * Any [data-foms-urgent-call][data-order-id] control (mobile order detail action
 * area, drawing workbench mobile toolbar) opens a bottom sheet that lists the
 * order's urgent-mention targets (GET /erp/api/orders/<id>/urgent-targets), lets
 * the user pick one + optional reason (≤500 chars, enforced client-side), then
 * POSTs /erp/api/orders/<id>/urgent-mention via window.FOMSNotificationWrite so the
 * same-origin write header is attached.
 *
 * Reuses the desktop urgent-mention order context (same endpoints); users without
 * access are rejected server-side (403) and see an error toast — no client gate.
 *
 * Loaded via foms_app_shell.html (fragment-replay entry), so all listeners are
 * document-delegated behind a window.__*_BOUND singleton guard (perf guard G4).
 */
(function () {
  'use strict';
  if (window.__FOMS_URGENT_CALL_BOUND) return;
  window.__FOMS_URGENT_CALL_BOUND = true;

  var SHEET_ID = 'erp-mobile-urgent-call-sheet';
  var MAX_MESSAGE = 500;
  var currentOrderId = null;
  var selectedTargetId = null;
  var targetsLoading = false;

  function esc(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function toast(message) {
    if (typeof window.fomsShowToast === 'function') {
      window.fomsShowToast(message);
    } else {
      window.alert(message);
    }
  }

  function getSheet() { return document.getElementById(SHEET_ID); }
  function hasOffcanvas() { return !!(window.bootstrap && window.bootstrap.Offcanvas); }
  function targetsEl() { return document.querySelector('[data-foms-urgent-targets]'); }
  function messageEl() { return document.querySelector('[data-foms-urgent-message]'); }
  function sendEl() { return document.querySelector('[data-foms-urgent-send]'); }

  function syncSendState() {
    var btn = sendEl();
    if (btn) btn.disabled = !(currentOrderId != null && selectedTargetId != null);
  }

  function selectTarget(btn) {
    selectedTargetId = btn.getAttribute('data-target-id');
    var container = targetsEl();
    if (container) {
      var all = container.querySelectorAll('[data-foms-urgent-target]');
      Array.prototype.forEach.call(all, function (el) {
        el.classList.toggle('is-selected', el === btn);
        el.setAttribute('aria-pressed', el === btn ? 'true' : 'false');
      });
    }
    syncSendState();
  }

  function groupByTeam(items) {
    // 서버가 팀 표시순→이름순으로 정렬해 보내므로, 최초 등장 순서를 그대로 유지한다.
    // team_label 이 없거나 비면 '기타' 로 묶는다(조용한 누락 금지).
    var order = [];
    var byLabel = {};
    items.forEach(function (u) {
      var label = (u && u.team_label && String(u.team_label)) || '기타';
      if (!byLabel[label]) { byLabel[label] = []; order.push(label); }
      byLabel[label].push(u);
    });
    return order.map(function (label) { return { label: label, members: byLabel[label] }; });
  }

  function targetButtonHtml(u) {
    var meta = [u.role].filter(Boolean).map(esc).join(' · ');
    return '<button type="button" class="erp-mobile-urgent-sheet__target"'
      + ' data-foms-urgent-target data-target-id="' + esc(u.id) + '" aria-pressed="false">'
      + '<span class="erp-mobile-urgent-sheet__target-name">' + esc(u.name) + '</span>'
      + (meta ? '<span class="erp-mobile-urgent-sheet__target-meta">' + meta + '</span>' : '')
      + '</button>';
  }

  function renderTargets(targets) {
    var container = targetsEl();
    if (!container) return;
    var items = Array.isArray(targets) ? targets : [];
    if (!items.length) {
      container.innerHTML = '<div class="erp-mobile-urgent-sheet__empty">'
        + '<i class="fas fa-user-slash" aria-hidden="true"></i>'
        + '<span>호출할 담당자가 없습니다.</span></div>';
      return;
    }
    var groups = groupByTeam(items);
    var openAll = groups.length <= 1; // 팀이 하나뿐이면 펼쳐 두고, 여러 팀이면 접어 둔다.
    container.innerHTML = groups.map(function (g) {
      var buttons = g.members.map(targetButtonHtml).join('');
      return '<details class="erp-mobile-urgent-sheet__team"' + (openAll ? ' open' : '') + '>'
        + '<summary class="erp-mobile-urgent-sheet__team-summary">'
        + '<span class="erp-mobile-urgent-sheet__team-name">' + esc(g.label) + '</span>'
        + '<span class="erp-mobile-urgent-sheet__team-count">' + g.members.length + '</span>'
        + '</summary>'
        + '<div class="erp-mobile-urgent-sheet__team-members">' + buttons + '</div>'
        + '</details>';
    }).join('');
  }

  function loadTargets(orderId) {
    var container = targetsEl();
    if (!container || targetsLoading) return;
    targetsLoading = true;
    container.innerHTML = '<div class="erp-mobile-urgent-sheet__placeholder" data-foms-urgent-placeholder>'
      + '<div class="spinner-border spinner-border-sm text-primary" role="status"></div> 대상 불러오는 중...</div>';

    fetch('/erp/api/orders/' + encodeURIComponent(orderId) + '/urgent-targets', {
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin'
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.success) throw new Error((data && data.message) || 'urgent-targets error');
        renderTargets(data.targets || []);
      })
      .catch(function (err) {
        console.error('urgent-targets load error:', err);
        var el = targetsEl();
        if (el) {
          el.innerHTML = '<div class="erp-mobile-urgent-sheet__error">'
            + '<i class="fas fa-exclamation-circle" aria-hidden="true"></i> 호출 대상을 불러오지 못했습니다.</div>';
        }
      })
      .finally(function () { targetsLoading = false; });
  }

  function openSheet(orderId) {
    var sheet = getSheet();
    if (!sheet || !hasOffcanvas()) return;
    currentOrderId = orderId;
    selectedTargetId = null;
    var msg = messageEl();
    if (msg) msg.value = '';
    syncSendState();
    window.bootstrap.Offcanvas.getOrCreateInstance(sheet).show();
    loadTargets(orderId);
  }

  function closeSheet() {
    var sheet = getSheet();
    if (sheet && sheet.classList.contains('show') && hasOffcanvas()) {
      window.bootstrap.Offcanvas.getOrCreateInstance(sheet).hide();
    }
  }

  function sendMention() {
    var btn = sendEl();
    if (!btn || btn.disabled) return;
    if (currentOrderId == null || selectedTargetId == null) return;
    var msgEl = messageEl();
    var message = msgEl ? String(msgEl.value || '').trim().slice(0, MAX_MESSAGE) : '';

    if (!window.FOMSNotificationWrite || typeof window.FOMSNotificationWrite.fetch !== 'function') {
      toast('긴급 호출을 보낼 수 없습니다.');
      return;
    }
    btn.disabled = true;
    window.FOMSNotificationWrite.fetch(
      '/erp/api/orders/' + encodeURIComponent(currentOrderId) + '/urgent-mention',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ target_user_id: parseInt(selectedTargetId, 10), message: message })
      }
    )
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.success) throw new Error((data && data.message) || '긴급 호출 발송 실패');
        toast(data.message || '긴급 호출을 보냈습니다.');
        closeSheet();
      })
      .catch(function (err) {
        console.error('urgent-mention error:', err);
        toast('긴급 호출 발송에 실패했습니다.');
        syncSendState();
      });
  }

  // ---- document-delegated events (swap-safe) --------------------------------
  document.addEventListener('click', function (e) {
    if (!e.target || !e.target.closest) return;

    var opener = e.target.closest('[data-foms-urgent-call]');
    if (opener) {
      e.preventDefault();
      var orderId = opener.getAttribute('data-order-id');
      if (orderId != null && orderId !== '') openSheet(orderId);
      return;
    }

    var targetBtn = e.target.closest('[data-foms-urgent-target]');
    if (targetBtn) { e.preventDefault(); selectTarget(targetBtn); return; }

    var sendBtn = e.target.closest('[data-foms-urgent-send]');
    if (sendBtn) { e.preventDefault(); sendMention(); return; }
  });
})();
