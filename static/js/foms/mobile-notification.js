/**
 * Mobile notification center — Phase 1A.
 *
 * Header bell(button) tap → bottom-sheet(offcanvas) with an unread badge and a
 * notification list that deep-links into the relevant surface. read / read-all /
 * archive actions are Phase 1B and intentionally out of scope here.
 *
 * Badge count SSOT: window.FOMSNotificationBadge (defined inline in
 * layout_scripts.html). This module only *subscribes* to that shared pub/sub —
 * it never fetches /erp/api/notifications/badge itself, so the desktop global
 * bell and this mobile bell share a single badge poll (no duplicate fetch).
 * The list uses the existing GET /erp/api/notifications (no backend change).
 *
 * Loaded via foms_app_shell.html which is a fragment-replay entry template, so
 * all listeners are document-delegated behind a window.__*_BOUND singleton guard
 * (perf guard G4 — idempotent across shell fragment swaps).
 */
(function () {
  'use strict';
  if (window.__FOMS_MOBILE_NOTIF_BOUND) return;
  window.__FOMS_MOBILE_NOTIF_BOUND = true;

  var SHEET_ID = 'erp-mobile-notification-sheet';
  var LIST_LIMIT = 30;
  var listLoading = false;

  function esc(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatTime(iso) {
    if (!iso) return '';
    // "YYYY-MM-DDTHH:MM:SS" / "YYYY-MM-DD HH:MM:SS" → "MM-DD HH:MM"
    return String(iso).substring(5, 16).replace('T', ' ');
  }

  function deepHref(noti) {
    if (noti.deep_link_url) return noti.deep_link_url;
    if (noti.order_id) return '/edit/' + noti.order_id + '?open=erp-order';
    return '';
  }

  // ---- badge (shared count) -------------------------------------------------
  function renderBadge(count) {
    var badge = document.querySelector('[data-foms-notif-badge]');
    if (!badge) return;
    var n = Number(count);
    if (!Number.isFinite(n) || n <= 0) {
      badge.hidden = true;
      badge.textContent = '0';
      return;
    }
    badge.textContent = n > 99 ? '99+' : String(n);
    badge.hidden = false;
  }

  function currentBadgeCount() {
    try {
      if (window.FOMSNotificationBadge && typeof window.FOMSNotificationBadge.getCount === 'function') {
        return window.FOMSNotificationBadge.getCount();
      }
    } catch (err) { /* noop */ }
    return 0;
  }

  function subscribeBadge() {
    if (window.FOMSNotificationBadge && typeof window.FOMSNotificationBadge.subscribe === 'function') {
      // subscribe() invokes the callback immediately with the current count and
      // again on every shared poll emit — no extra network request is issued.
      window.FOMSNotificationBadge.subscribe('mobile-shell-notify-badge', renderBadge);
    } else {
      renderBadge(0);
    }
  }

  // ---- list rendering -------------------------------------------------------
  function itemHtml(noti) {
    var unread = !noti.is_read;
    var urgent = !!noti.is_urgent;
    var href = deepHref(noti);
    var tag = href ? 'a' : 'div';
    var hrefAttr = href ? ' href="' + esc(href) + '"' : '';
    var cls = 'erp-mobile-notif-item'
      + (unread ? ' is-unread' : '')
      + (urgent ? ' is-urgent' : '');
    var flag = urgent ? '<span class="erp-mobile-notif-item__flag">긴급</span> ' : '';
    var message = noti.message
      ? '<p class="erp-mobile-notif-item__msg">' + esc(noti.message) + '</p>'
      : '';
    return '<' + tag + ' class="' + cls + '" data-foms-notif-item' + hrefAttr + '>'
      + '<div class="erp-mobile-notif-item__head">'
      + '<strong class="erp-mobile-notif-item__title">' + flag + esc(noti.title) + '</strong>'
      + '<time class="erp-mobile-notif-item__time">' + esc(formatTime(noti.created_at)) + '</time>'
      + '</div>'
      + message
      + '</' + tag + '>';
  }

  function renderList(notifications) {
    var listEl = document.querySelector('[data-foms-notif-list]');
    var urgentEl = document.querySelector('[data-foms-notif-urgent]');
    if (!listEl) return;

    if (urgentEl) {
      urgentEl.hidden = true;
      urgentEl.innerHTML = '';
    }

    var items = Array.isArray(notifications) ? notifications : [];
    if (!items.length) {
      listEl.innerHTML = '<div class="erp-mobile-notif-empty">'
        + '<i class="far fa-bell-slash" aria-hidden="true"></i>'
        + '<span>알림이 없습니다.</span></div>';
      return;
    }

    var urgent = items.filter(function (n) { return n.is_urgent && !n.is_read; });
    var rest = items.filter(function (n) { return !(n.is_urgent && !n.is_read); });

    if (urgentEl && urgent.length) {
      urgentEl.innerHTML = '<div class="erp-mobile-notif-sheet__urgent-label">긴급 · 확인 필요</div>'
        + urgent.map(itemHtml).join('');
      urgentEl.hidden = false;
    }
    listEl.innerHTML = rest.map(itemHtml).join('');
  }

  function loadList() {
    var listEl = document.querySelector('[data-foms-notif-list]');
    if (!listEl || listLoading) return;
    listLoading = true;
    listEl.innerHTML = '<div class="erp-mobile-notif-sheet__placeholder" data-foms-notif-placeholder>'
      + '<div class="spinner-border spinner-border-sm text-primary" role="status"></div> 로딩 중...</div>';

    fetch('/erp/api/notifications?limit=' + LIST_LIMIT, {
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin'
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.success) throw new Error('notification API error');
        renderList(data.notifications || []);
      })
      .catch(function (err) {
        console.error('mobile notification list error:', err);
        var el = document.querySelector('[data-foms-notif-list]');
        if (el) {
          el.innerHTML = '<div class="erp-mobile-notif-error">'
            + '<i class="fas fa-exclamation-circle" aria-hidden="true"></i> 알림을 불러오지 못했습니다.</div>';
        }
      })
      .finally(function () { listLoading = false; });
  }

  // ---- sheet open / close ---------------------------------------------------
  function getSheet() { return document.getElementById(SHEET_ID); }

  function hasOffcanvas() {
    return !!(window.bootstrap && window.bootstrap.Offcanvas);
  }

  function setExpanded(state) {
    var btn = document.querySelector('[data-foms-notif-open]');
    if (btn) btn.setAttribute('aria-expanded', state ? 'true' : 'false');
  }

  function openSheet() {
    var sheet = getSheet();
    if (!sheet || !hasOffcanvas()) return;
    var oc = window.bootstrap.Offcanvas.getOrCreateInstance(sheet);
    // Reset aria-expanded when closed via backdrop / ESC / close button.
    if (sheet.dataset.fomsNotifHideBound !== '1') {
      sheet.dataset.fomsNotifHideBound = '1';
      sheet.addEventListener('hidden.bs.offcanvas', function () { setExpanded(false); });
    }
    oc.show();
    setExpanded(true);
    loadList();
  }

  function closeSheet() {
    var sheet = getSheet();
    if (sheet && sheet.classList.contains('show') && hasOffcanvas()) {
      window.bootstrap.Offcanvas.getOrCreateInstance(sheet).hide();
    }
    setExpanded(false);
  }

  function toggleSheet() {
    var sheet = getSheet();
    if (!sheet) return;
    if (sheet.classList.contains('show')) {
      closeSheet();
    } else {
      openSheet();
    }
  }

  // ---- document-delegated events (swap-safe) --------------------------------
  document.addEventListener('click', function (e) {
    if (!e.target || !e.target.closest) return;

    var opener = e.target.closest('[data-foms-notif-open]');
    if (opener) {
      e.preventDefault();
      toggleSheet();
      return;
    }

    // Item tap → close the sheet and let navigation proceed. The anchor href is
    // handled by erp-shell fragment nav for /erp/* (its capture-phase listener
    // runs first) or a normal browser navigation otherwise.
    var item = e.target.closest('[data-foms-notif-item]');
    if (item) {
      closeSheet();
    }
  });

  function init() {
    subscribeBadge();
    renderBadge(currentBadgeCount());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Header (incl. the badge span) is re-rendered on each shell fragment swap;
  // repaint the badge from the shared count so it survives the swap.
  document.addEventListener('foms:main-content-swapped', function () {
    renderBadge(currentBadgeCount());
  });
})();
