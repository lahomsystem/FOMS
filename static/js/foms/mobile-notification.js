/**
 * Mobile notification center — Phase 1A + 1B + 2.
 *
 * Header bell(button) tap → bottom-sheet(offcanvas) with an unread badge and a
 * notification list that deep-links into the relevant surface.
 *
 * Phase 1B activates the sheet write actions (all via window.FOMSNotificationWrite
 * so the same-origin write header is attached): tapping an unread item marks it
 * read *before* navigating (await, but navigation proceeds even on failure), a
 * header "모두 읽음"/"모두 보관" pair calls read-all/archive-all, and each item has
 * a single archive button. Phase 2 adds an "확인(ack)" button to pinned urgent
 * items; ack'd urgent items drop out of the pinned section (pinned = is_urgent &&
 * !ack_at, not the Phase 1A is_urgent && !is_read).
 *
 * Badge count SSOT: window.FOMSNotificationBadge (defined inline in
 * layout_scripts.html). This module only *subscribes* to that shared pub/sub for
 * rendering — it never fetches /erp/api/notifications/badge itself, so the desktop
 * global bell and this mobile bell share a single badge poll (no duplicate fetch).
 * After a write it calls FOMSNotificationBadge.refresh({force:true}) to re-sync.
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

  // ---- write helper ---------------------------------------------------------
  function writeFetch(url) {
    // 모든 상태 변경 POST 는 same-origin write 헤더가 붙는 공용 helper 를 경유한다.
    if (window.FOMSNotificationWrite && typeof window.FOMSNotificationWrite.fetch === 'function') {
      return window.FOMSNotificationWrite.fetch(url, { method: 'POST', headers: { 'Accept': 'application/json' } });
    }
    return Promise.reject(new Error('FOMSNotificationWrite unavailable'));
  }

  function postWrite(url) {
    // Promise<boolean> — 성공(success:true) 여부. 실패는 삼키지 않고 호출부에 알린다.
    return writeFetch(url)
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.success) throw new Error((data && data.message) || 'notification write error');
        return true;
      });
  }

  function refreshBadge() {
    try {
      if (window.FOMSNotificationBadge && typeof window.FOMSNotificationBadge.refresh === 'function') {
        window.FOMSNotificationBadge.refresh({ force: true });
      }
    } catch (err) { /* noop */ }
  }

  function toast(message) {
    if (typeof window.fomsShowToast === 'function') {
      window.fomsShowToast(message);
    } else {
      window.alert(message);
    }
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
  function itemHtml(noti, pinned) {
    var unread = !noti.is_read;
    var urgent = !!noti.is_urgent;
    var href = deepHref(noti);
    var id = noti.id;
    var cls = 'erp-mobile-notif-item'
      + (unread ? ' is-unread' : '')
      + (urgent ? ' is-urgent' : '');
    var flag = urgent ? '<span class="erp-mobile-notif-item__flag">긴급</span> ' : '';
    var message = noti.message
      ? '<p class="erp-mobile-notif-item__msg">' + esc(noti.message) + '</p>'
      : '';
    // The clickable body is an <a> when a deep link exists; action buttons are
    // siblings (never nested inside the anchor → valid, tap-safe HTML).
    var bodyTag = href ? 'a' : 'div';
    var hrefAttr = href ? ' href="' + esc(href) + '" data-foms-notif-href="' + esc(href) + '"' : '';
    var body = '<' + bodyTag + ' class="erp-mobile-notif-item__body" data-foms-notif-item'
      + hrefAttr + '>'
      + '<div class="erp-mobile-notif-item__head">'
      + '<strong class="erp-mobile-notif-item__title">' + flag + esc(noti.title) + '</strong>'
      + '<time class="erp-mobile-notif-item__time">' + esc(formatTime(noti.created_at)) + '</time>'
      + '</div>'
      + message
      + '</' + bodyTag + '>';

    var actions = '';
    if (pinned && id != null) {
      actions += '<button type="button" class="erp-mobile-notif-item__act erp-mobile-notif-item__act--ack"'
        + ' data-foms-notif-ack data-foms-notif-id="' + esc(id) + '">'
        + '<i class="fas fa-check" aria-hidden="true"></i> 확인</button>';
    }
    if (id != null) {
      actions += '<button type="button" class="erp-mobile-notif-item__act erp-mobile-notif-item__act--archive"'
        + ' data-foms-notif-archive-item data-foms-notif-id="' + esc(id) + '"'
        + ' aria-label="이 알림 보관" title="보관">'
        + '<i class="fas fa-box-archive" aria-hidden="true"></i></button>';
    }

    return '<div class="' + cls + '" data-foms-notif-row'
      + (id != null ? ' data-foms-notif-id="' + esc(id) + '"' : '')
      + (unread ? ' data-foms-notif-unread="1"' : '') + '>'
      + body
      + (actions ? '<div class="erp-mobile-notif-item__actions">' + actions + '</div>' : '')
      + '</div>';
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

    // Pinned urgent = 아직 ack 하지 않은 긴급(P0). ack 하면 일반 목록으로 내려간다.
    var urgent = items.filter(function (n) { return n.is_urgent && !n.ack_at; });
    var rest = items.filter(function (n) { return !(n.is_urgent && !n.ack_at); });

    if (urgentEl && urgent.length) {
      urgentEl.innerHTML = '<div class="erp-mobile-notif-sheet__urgent-label">긴급 · 확인 필요</div>'
        + urgent.map(function (n) { return itemHtml(n, true); }).join('');
      urgentEl.hidden = false;
    }
    listEl.innerHTML = rest.map(function (n) { return itemHtml(n, false); }).join('');
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

  // ---- write actions (Phase 1B / 2) -----------------------------------------
  function navigateTo(href) {
    if (href) window.location.assign(href);
  }

  function onItemNav(bodyEl) {
    // 미읽음이면 read POST 를 await 한 뒤 이동한다(실패해도 이동은 진행). 이동 후
    // 페이지가 새로 로드되며 badge 는 공유 poll 로 재동기화된다.
    var href = bodyEl.getAttribute('data-foms-notif-href') || '';
    var row = bodyEl.closest('[data-foms-notif-row]');
    var unread = !!(row && row.getAttribute('data-foms-notif-unread') === '1');
    var id = row ? row.getAttribute('data-foms-notif-id') : null;
    closeSheet();

    if (!unread || id == null) {
      navigateTo(href);
      return;
    }
    postWrite('/erp/api/notifications/' + encodeURIComponent(id) + '/read')
      .then(function () {
        // 미읽음 시각 상태 즉시 갱신(no-href 항목은 이동하지 않으므로 목록에 반영된다).
        if (row) {
          row.classList.remove('is-unread');
          row.removeAttribute('data-foms-notif-unread');
        }
        refreshBadge();
      })
      .catch(function (err) { console.error('notification read error:', err); })
      .finally(function () { navigateTo(href); });
  }

  function onArchiveItem(btn) {
    var id = btn.getAttribute('data-foms-notif-id');
    if (id == null) return;
    if (btn.disabled) return;
    btn.disabled = true;
    postWrite('/erp/api/notifications/' + encodeURIComponent(id) + '/archive')
      .then(function () {
        var row = btn.closest('[data-foms-notif-row]');
        if (row && row.parentNode) row.parentNode.removeChild(row);
        refreshBadge();
      })
      .catch(function (err) {
        console.error('notification archive error:', err);
        btn.disabled = false;
        toast('알림 보관에 실패했습니다.');
      });
  }

  function onAck(btn) {
    var id = btn.getAttribute('data-foms-notif-id');
    if (id == null) return;
    if (btn.disabled) return;
    btn.disabled = true;
    postWrite('/erp/api/notifications/' + encodeURIComponent(id) + '/ack')
      .then(function () {
        refreshBadge();
        loadList();  // ack 한 긴급은 pinned 에서 빠지고 일반 목록으로 재배치된다.
      })
      .catch(function (err) {
        console.error('notification ack error:', err);
        btn.disabled = false;
        toast('긴급 알림 확인에 실패했습니다.');
      });
  }

  function onReadAll(btn) {
    if (btn && btn.disabled) return;
    if (btn) btn.disabled = true;
    postWrite('/erp/api/notifications/read-all')
      .then(function () { refreshBadge(); loadList(); })
      .catch(function (err) {
        console.error('notification read-all error:', err);
        toast('모두 읽음 처리에 실패했습니다.');
      })
      .finally(function () { if (btn) btn.disabled = false; });
  }

  function onArchiveAll(btn) {
    if (btn && btn.disabled) return;
    if (!window.confirm('모든 알림을 보관하시겠습니까?')) return;
    if (btn) btn.disabled = true;
    postWrite('/erp/api/notifications/archive-all')
      .then(function () { refreshBadge(); loadList(); })
      .catch(function (err) {
        console.error('notification archive-all error:', err);
        toast('모두 보관에 실패했습니다.');
      })
      .finally(function () { if (btn) btn.disabled = false; });
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
  // Opener lives in the shell header (outside the sheet) → simple bubble listener.
  document.addEventListener('click', function (e) {
    if (!e.target || !e.target.closest) return;
    var opener = e.target.closest('[data-foms-notif-open]');
    if (opener) {
      e.preventDefault();
      toggleSheet();
    }
  });

  // Sheet-internal actions run in the CAPTURE phase so that item taps mark-read
  // *before* (and instead of) the erp-shell capture nav listener — read/ack/archive
  // buttons that live inside an <a>-adjacent row never trigger navigation.
  document.addEventListener('click', function (e) {
    if (!e.target || !e.target.closest) return;

    var ackBtn = e.target.closest('[data-foms-notif-ack]');
    if (ackBtn) { e.preventDefault(); e.stopImmediatePropagation(); onAck(ackBtn); return; }

    var archiveBtn = e.target.closest('[data-foms-notif-archive-item]');
    if (archiveBtn) { e.preventDefault(); e.stopImmediatePropagation(); onArchiveItem(archiveBtn); return; }

    var readAll = e.target.closest('[data-foms-notif-read-all]');
    if (readAll) { e.preventDefault(); e.stopImmediatePropagation(); onReadAll(readAll); return; }

    var archiveAll = e.target.closest('[data-foms-notif-archive-all]');
    if (archiveAll) { e.preventDefault(); e.stopImmediatePropagation(); onArchiveAll(archiveAll); return; }

    var body = e.target.closest('[data-foms-notif-item]');
    if (body) { e.preventDefault(); e.stopImmediatePropagation(); onItemNav(body); return; }
  }, true);

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
