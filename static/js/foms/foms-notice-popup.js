/**
 * FOMS 공지 창 · 공지 목록 읽음 표시(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §5).
 *
 * 1) 공지 창(본사 공용 레이아웃, partials/shared/notice_popup.html): 페이지를 열 때 GET /api/notices 를 한 번 부른다.
 *    → {success, data:{items:[{id,title,body,display_mode,acked,read,created_by_name,created_at,...}], unread}, error}
 *    "확인 창"(POPUP) 공지 중 확인 안 한 것이 있으면 가운데 흰 창. "확인"을 눌러야만 닫힌다(배경 · Esc 로 안 닫힘).
 *    확인: POST /api/notices/<id>/ack → {pending:[...남은 창 공지]} — 남은 게 있으면 다음 공지("2 / 2"), 없으면 닫는다.
 *    긴급(빨간 전체 화면, foms-urgent-alert.js)과는 다른 창이다 — 겹치면 긴급 창이 위(z-index, foms-notice.css).
 * 2) 메뉴 안 읽음 수: 같은 응답의 unread 로 [data-foms-notice-unread] 를 채운다(0 이면 숨김).
 * 3) 공지 목록(/notices · /partner/notices, notices/_items.html): 펼치면 POST /api/notices/<id>/read 로 읽음.
 */
(function () {
  'use strict';

  var MAX_POPUPS = 5;

  function setBadges(count) {
    var n = Number(count) || 0;
    document.querySelectorAll('[data-foms-notice-unread]').forEach(function (el) {
      el.textContent = n > 99 ? '99+' : String(n);
      el.hidden = n <= 0;
    });
    document.querySelectorAll('[data-foms-notice-unread-count]').forEach(function (el) {
      el.textContent = String(n);
    });
  }

  function idUrl(template, id) {
    return String(template || '').replace('/0/', '/' + encodeURIComponent(String(id)) + '/');
  }

  async function postJson(url) {
    var resp = await fetch(url, { method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json' } });
    var data = null;
    try { data = await resp.json(); } catch (e) { data = null; }
    if (!data || !data.success) throw new Error((data && data.error) || '저장하지 못했습니다. 다시 눌러 주세요.');
    return data.data || {};
  }

  // ---- 1) 공지 창 ----
  function bindPopup(root, pending) {
    var ackUrl = root.getAttribute('data-ack-url') || '';
    var title = root.querySelector('[data-foms-notice-title]');
    var body = root.querySelector('[data-foms-notice-body]');
    var meta = root.querySelector('[data-foms-notice-meta]');
    var count = root.querySelector('[data-foms-notice-count]');
    var status = root.querySelector('[data-foms-notice-status]');
    var ok = root.querySelector('[data-foms-notice-ok]');
    if (!ok) return;
    var total = pending.length;
    var index = 0;
    var current = null;

    function show(notice) {
      current = notice;
      if (title) title.textContent = notice.title || '';
      if (body) body.textContent = notice.body || '';
      if (meta) meta.textContent = [notice.created_by_name, notice.created_at].filter(Boolean).join(' · ');
      if (count) count.textContent = total > 1 ? (index + 1) + ' / ' + total : '';
      if (status) { status.textContent = ''; status.classList.remove('is-error'); }
      ok.focus();
    }

    function close() {
      root.hidden = true;
      document.documentElement.classList.remove('foms-notice-open');
    }

    // 창 밖으로 초점이 나가지 않게 — 단추가 하나라 Tab 도 그 단추에 머문다. Esc 는 무시한다.
    root.addEventListener('keydown', function (ev) {
      if (ev.key === 'Tab' || ev.key === 'Escape') {
        ev.preventDefault();
        ok.focus();
      }
    });

    ok.addEventListener('click', async function () {
      if (!current) return;
      ok.disabled = true;
      try {
        var data = await postJson(idUrl(ackUrl, current.id));
        var next = Array.isArray(data.pending) ? data.pending : [];
        if (next.length) {
          index += 1;
          total = Math.max(total, index + next.length);
          show(next[0]);
        } else {
          close();
        }
      } catch (err) {
        if (status) { status.textContent = err.message; status.classList.add('is-error'); }
      }
      ok.disabled = false;
    });

    root.hidden = false;
    document.documentElement.classList.add('foms-notice-open');
    show(pending[0]);
  }

  async function loadPopup(root) {
    var url = root.getAttribute('data-list-url');
    if (!url) return;
    try {
      var resp = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      var data = null;
      try { data = await resp.json(); } catch (e) { data = null; }
      if (!data || !data.success || !data.data) return;
      setBadges(data.data.unread);
      var items = Array.isArray(data.data.items) ? data.data.items : [];
      var pending = items
        .filter(function (n) { return n && n.display_mode === 'POPUP' && !n.acked; })
        .sort(function (a, b) { return Number(a.id) - Number(b.id); }) // 오래된 것부터(서버 pending_popups 와 같은 차례)
        .slice(0, MAX_POPUPS);
      if (pending.length) bindPopup(root, pending);
    } catch (e) {
      // 공지 창은 보조 기능 — 불러오지 못해도 화면 작업은 막지 않는다(다음 페이지에서 다시 부른다).
    }
  }

  // ---- 3) 공지 목록 읽음 ----
  function bindList(list) {
    var readUrl = list.getAttribute('data-read-url') || '';
    list.addEventListener('toggle', async function (ev) {
      var item = ev.target;
      if (!item || !item.matches || !item.matches('[data-foms-notice-item]')) return;
      if (!item.open || item.getAttribute('data-read') === '1') return;
      item.setAttribute('data-read', '1');
      try {
        await postJson(idUrl(readUrl, item.getAttribute('data-notice-id')));
        item.classList.remove('is-unread');
        var label = item.querySelector('[data-foms-notice-unread-label]');
        if (label) label.remove();
        var counter = list.querySelector('[data-foms-notice-unread-count]');
        setBadges(Math.max((counter ? Number(counter.textContent) || 0 : 1) - 1, 0));
      } catch (err) {
        item.setAttribute('data-read', '0'); // 다음에 펼칠 때 다시 남긴다
      }
    }, true); // toggle 은 버블링하지 않는다 — 잡기 단계로 받는다
  }

  document.addEventListener('DOMContentLoaded', function () {
    var list = document.querySelector('[data-foms-notice-list]');
    if (list) bindList(list);
    var root = document.querySelector('[data-foms-notice-popup]');
    // 협력사 화면(자기 공지 창 data-pp-notice)에서는 돌지 않는다 — 협력사 레이아웃은 이 창을 싣지 않지만 한 번 더 막는다.
    if (root && !document.querySelector('[data-pp-notice]')) loadPopup(root);
  });
})();
