/**
 * MOBILE-DELETE-01 — 모바일 주문 삭제(휴지통 이동) + 5초 되돌리기.
 *
 * 상세 페이지: 헤더 ⋯(data-foms-more-open) → 더보기 시트 → 확인 시트(사유 칩 + 길게 눌러 삭제)
 *   → POST /api/orders/<id>/mobile-delete → sessionStorage 에 되돌리기 정보 → 목록으로 이동.
 * 목록 페이지: sessionStorage 에 남은 되돌리기 정보가 있으면 토스트를 그린다(5초, 되돌리기 →
 *   POST /api/orders/<id>/mobile-restore).
 *
 * 노출 판정은 서버가 한다(#foms-mobile-delete-root 가 없으면 이 스크립트는 토스트만 담당).
 * CSRF 는 csrf_bootstrap 이 fetch 를 감싸 X-CSRF-Token 을 싣는다.
 */
(function () {
  'use strict';

  var HOLD_MS = 1500;
  var UNDO_KEY = 'foms:mdel:undo';

  function qs(sel, root) { return (root || document).querySelector(sel); }

  function readUndo() {
    try {
      var raw = window.sessionStorage.getItem(UNDO_KEY);
      if (!raw) { return null; }
      var obj = JSON.parse(raw);
      return (obj && typeof obj === 'object') ? obj : null;
    } catch (e) { return null; }
  }
  function writeUndo(obj) {
    try { window.sessionStorage.setItem(UNDO_KEY, JSON.stringify(obj)); } catch (e) { /* private mode */ }
  }
  function clearUndo() {
    try { window.sessionStorage.removeItem(UNDO_KEY); } catch (e) { /* noop */ }
  }

  async function postJson(url, body) {
    var res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify(body || {})
    });
    var data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!data || typeof data !== 'object') {
      data = { success: false, code: 'BAD_RESPONSE', error: '서버 응답을 읽지 못했어요.' };
    }
    data.__status = res.status;
    return data;
  }

  // ---------------------------------------------------------------- toast
  function showToast(text, opts) {
    opts = opts || {};
    var old = qs('.foms-mdel-toast');
    if (old) { old.remove(); }
    var el = document.createElement('div');
    el.className = 'foms-mdel-toast';
    el.setAttribute('role', 'status');
    el.setAttribute('aria-live', 'polite');
    var msg = document.createElement('span');
    msg.className = 'foms-mdel-toast__msg';
    msg.textContent = text;
    el.appendChild(msg);
    if (opts.actionLabel && typeof opts.onAction === 'function') {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'foms-mdel-toast__action';
      btn.textContent = opts.actionLabel;
      btn.addEventListener('click', function () { opts.onAction(el, btn); });
      el.appendChild(btn);
    }
    if (opts.duration) {
      var bar = document.createElement('span');
      bar.className = 'foms-mdel-toast__bar';
      el.appendChild(bar);
      requestAnimationFrame(function () {
        bar.style.setProperty('--foms-mdel-toast-ms', opts.duration + 'ms');
        el.classList.add('is-counting');
      });
      el.__timer = setTimeout(function () {
        el.classList.add('is-leaving');
        setTimeout(function () { el.remove(); }, 250);
        if (typeof opts.onExpire === 'function') { opts.onExpire(); }
      }, opts.duration);
    }
    document.body.appendChild(el);
    return el;
  }

  function renderUndoToastIfAny() {
    var undo = readUndo();
    if (!undo || !undo.order_id) { return; }
    clearUndo();
    var remaining = (undo.until || 0) - Date.now();
    if (remaining <= 300) { return; }
    var label = '휴지통으로 옮겼어요' + (undo.customer_name ? ' · ' + undo.customer_name : '');
    showToast(label, {
      actionLabel: '되돌리기',
      duration: Math.min(remaining, (undo.undo_seconds || 5) * 1000),
      onAction: async function (el, btn) {
        btn.disabled = true;
        if (el.__timer) { clearTimeout(el.__timer); }
        try {
          var data = await postJson('/api/orders/' + undo.order_id + '/mobile-restore', {});
          if (!data.success) {
            showToast(data.error || data.message || '되돌리지 못했어요. PC 휴지통에서 복원해 주세요.');
            return;
          }
          showToast('되돌렸어요', { duration: 1800 });
          setTimeout(function () { window.location.reload(); }, 900);
        } catch (e) {
          showToast('네트워크 오류로 되돌리지 못했어요. PC 휴지통에서 복원해 주세요.');
        }
      }
    });
  }

  // ---------------------------------------------------------------- sheets
  function mount(tplId) {
    var tpl = document.getElementById(tplId);
    if (!tpl) { return null; }
    var host = document.createElement('div');
    host.className = 'foms-mdel-layer';
    host.appendChild(tpl.content.cloneNode(true));
    document.body.appendChild(host);
    document.body.classList.add('foms-mdel-lock');
    host.querySelectorAll('[data-mdel-close]').forEach(function (b) {
      b.addEventListener('click', function () { unmount(host); });
    });
    return host;
  }
  function unmount(host) {
    if (host && host.parentNode) { host.parentNode.removeChild(host); }
    if (!qs('.foms-mdel-layer')) { document.body.classList.remove('foms-mdel-lock'); }
    var more = qs('[data-foms-more-open]');
    if (more) { more.setAttribute('aria-expanded', 'false'); }
  }

  function openMenu(root) {
    var host = mount('foms-mdel-menu-tpl');
    if (!host) { return; }
    var more = qs('[data-foms-more-open]');
    if (more) { more.setAttribute('aria-expanded', 'true'); }
    var blocked = root.getAttribute('data-guard-level') === 'blocked';
    var del = qs('[data-mdel-open-confirm]', host);
    var lock = qs('[data-mdel-blocked]', host);
    if (blocked) {
      del.hidden = true;
      lock.hidden = false;
      lock.disabled = true;
    } else {
      del.addEventListener('click', function () { unmount(host); openConfirm(root); });
    }
  }

  function openConfirm(root) {
    var host = mount('foms-mdel-confirm-tpl');
    if (!host) { return; }
    var level = root.getAttribute('data-guard-level') || 'warn';
    var reason = null;
    var note = '';

    qs('[data-mdel-target-name]', host).textContent = root.getAttribute('data-target-name') || '';
    qs('[data-mdel-target-meta]', host).textContent = root.getAttribute('data-target-meta') || '';

    var warn = qs('[data-mdel-warn]', host);
    if (level === 'warn') {
      warn.hidden = false;
      qs('[data-mdel-warn-text]', host).textContent = root.getAttribute('data-guard-label') || '';
      qs('[data-mdel-reason-label]', host).textContent = '삭제 이유 (필수)';
    }

    var noteInput = qs('[data-mdel-note]', host);
    var hold = qs('[data-mdel-hold]', host);
    var fill = qs('[data-mdel-fill]', host);
    var holdLabel = qs('[data-mdel-hold-label]', host);

    function refresh() {
      var ok = !!reason && (reason !== 'other' || note.length > 0);
      hold.disabled = !ok;
      holdLabel.textContent = ok ? '길게 눌러 삭제' : (reason === 'other' ? '이유를 적어주세요' : '이유를 먼저 선택하세요');
    }

    host.querySelectorAll('[data-mdel-reason]').forEach(function (chip) {
      chip.addEventListener('click', function () {
        host.querySelectorAll('[data-mdel-reason]').forEach(function (c) {
          c.classList.remove('is-on');
          c.setAttribute('aria-checked', 'false');
        });
        chip.classList.add('is-on');
        chip.setAttribute('aria-checked', 'true');
        reason = chip.getAttribute('data-mdel-reason');
        if (reason === 'other') {
          noteInput.hidden = false;
          noteInput.focus();
        } else {
          noteInput.hidden = true;
        }
        refresh();
      });
    });
    noteInput.addEventListener('input', function () {
      note = noteInput.value.trim();
      refresh();
    });

    // 길게 누르기: pointerdown 으로 시작, 손을 떼거나 벗어나면 취소.
    var raf = null;
    var started = 0;
    var firing = false;
    function stop() {
      if (raf) { cancelAnimationFrame(raf); raf = null; }
      fill.style.width = '0%';
    }
    function tick() {
      var p = Math.min(1, (performance.now() - started) / HOLD_MS);
      fill.style.width = (p * 100) + '%';
      if (p >= 1) { raf = null; fire(); return; }
      raf = requestAnimationFrame(tick);
    }
    hold.addEventListener('pointerdown', function (e) {
      if (hold.disabled || firing) { return; }
      e.preventDefault();
      try { hold.setPointerCapture(e.pointerId); } catch (err) { /* optional */ }
      started = performance.now();
      raf = requestAnimationFrame(tick);
    });
    ['pointerup', 'pointercancel', 'pointerleave'].forEach(function (ev) {
      hold.addEventListener(ev, function () { if (!firing) { stop(); } });
    });
    hold.addEventListener('contextmenu', function (e) { e.preventDefault(); });

    async function fire() {
      if (firing) { return; }
      firing = true;
      hold.disabled = true;
      holdLabel.textContent = '삭제 중…';
      if (navigator.vibrate) { try { navigator.vibrate(30); } catch (e) { /* noop */ } }
      var orderId = root.getAttribute('data-order-id');
      var version = parseInt(root.getAttribute('data-mutation-version') || '0', 10);
      try {
        var data = await postJson('/api/orders/' + orderId + '/mobile-delete', {
          reason_code: reason,
          reason_note: reason === 'other' ? note : '',
          mutation_version: version || undefined
        });
        if (!data.success) {
          firing = false;
          stop();
          refresh();
          var msg = data.error || data.message || '삭제하지 못했어요.';
          if (data.code === 'REVISION_CONFLICT') { msg = '다른 곳에서 바뀐 주문이에요. 새로고침 후 다시 해주세요.'; }
          if (data.__status === 403) { console.warn('[mobile-delete] 403 — 메뉴 노출과 서버 게이트 불일치', data); }
          showToast(msg, { duration: 3200 });
          return;
        }
        var d = data.data || {};
        writeUndo({
          order_id: d.order_id || orderId,
          customer_name: d.customer_name || '',
          undo_seconds: d.undo_seconds || 5,
          until: Date.now() + ((d.undo_seconds || 5) * 1000)
        });
        var returnTo = root.getAttribute('data-return-to') || '/';
        window.location.assign(returnTo);
      } catch (e) {
        firing = false;
        stop();
        refresh();
        showToast('네트워크 오류로 삭제하지 못했어요.', { duration: 3200 });
      }
    }
  }

  function init() {
    renderUndoToastIfAny();
    var root = document.getElementById('foms-mobile-delete-root');
    if (!root) { return; }
    var more = qs('[data-foms-more-open]');
    if (!more) { return; }
    more.addEventListener('click', function () {
      if (qs('.foms-mdel-layer')) { return; }
      openMenu(root);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
