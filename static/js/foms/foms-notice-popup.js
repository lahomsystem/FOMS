/**
 * FOMS 공지 창 · 공지 목록 읽음 표시(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §5).
 *
 * 1) 공지 창(본사 공용 레이아웃, partials/shared/notice_popup.html): 페이지를 열 때 GET /api/notices?view=popup 을 한 번 부른다.
 *    → {success, data:{pending:[{id,title,body,created_by_name,created_at,images}], unread}, error} — 목록 본문은 싣지 않는다.
 *    images([{url, thumb_url, name}])는 창 안 썸네일 줄 — 누르면 사진 창(foms-notice-gallery.js, 설계서 §8)이 공지 창 위에 뜬다.
 *    확인 안 한 "확인 창" 공지가 있으면 가운데 흰 창. "확인"을 눌러야만 닫힌다(배경 · Esc 로 안 닫힘).
 *    확인: POST /api/notices/<id>/ack → {pending:[...남은 창 공지], unread} — 남은 게 있으면 다음 공지("2 / 2"), 없으면 닫는다.
 *    404(그새 지웠거나 · 기간이 끝났거나 · 받는 쪽이 바뀜) 등 4xx 는 "이미 끝난 공지"로 보고 다음으로 넘어간다.
 *    오류 글을 남기고 창을 그대로 두는 것은 네트워크 오류 · 5xx 뿐이다(다시 누르면 된다).
 *    초점은 창 안 "확인" 단추에 가둔다(document 잡기 단계 focusin · keydown, 닫히면 푼다). 긴급 창 · 도면 확인창처럼
 *    더 위에 뜨는 창이 열려 있으면 가두지 않는다(서로 초점을 뺏지 않게). 겹치면 그 창들이 위(z-index, foms-notice.css).
 *    공지 사진 창(.foms-notice-gallery)도 "더 위 창"이다 — 열려 있는 동안 가두기를 쉬고, 닫으면 공지 창은 그대로다.
 * 2) 메뉴 안 읽음 수: 같은 응답의 unread 로 [data-foms-notice-unread] 를 채운다(0 이면 숨김).
 * 3) 공지 목록(/notices · /partner/notices, notices/_items.html): 펼치면 POST /api/notices/<id>/read 로 읽음.
 */
(function () {
  'use strict';

  var MAX_POPUPS = 5;
  // 공지 창보다 위에 뜨는 창(긴급 106000 · 도면 확인 105500 · 공지 사진 창 105460) — 열려 있으면 초점 가두기를 쉰다.
  var HIGHER = '#foms-urgent-alert, .foms-drawing-alert:not([hidden]), .foms-notice-gallery:not([hidden])';

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

  // 결과: {ok:true, data} | {ok:false, gone:true}(4xx — 이미 끝난 공지) — 네트워크 오류 · 5xx 는 Error 를 던진다.
  async function postJson(url) {
    var resp = await fetch(url, { method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json' } });
    var data = null;
    try { data = await resp.json(); } catch (e) { data = null; }
    if (resp.ok && data && data.success) return { ok: true, data: data.data || {} };
    if (resp.status >= 400 && resp.status < 500) return { ok: false, gone: true };
    throw new Error((data && data.error) || '저장하지 못했습니다. 다시 눌러 주세요.');
  }

  // ---- 1) 공지 창 ----
  function bindPopup(root, pending) {
    var ackUrl = root.getAttribute('data-ack-url') || '';
    var title = root.querySelector('[data-foms-notice-title]');
    var body = root.querySelector('[data-foms-notice-body]');
    var meta = root.querySelector('[data-foms-notice-meta]');
    var count = root.querySelector('[data-foms-notice-count]');
    var status = root.querySelector('[data-foms-notice-status]');
    var images = root.querySelector('[data-foms-notice-images]');
    var ok = root.querySelector('[data-foms-notice-ok]');
    if (!ok) return;
    var queue = pending.slice(0, MAX_POPUPS); // queue[0] = 지금 보이는 공지
    var total = queue.length;
    var index = 0;

    function higherOpen() { return !!document.querySelector(HIGHER); }

    // 창 밖으로 초점이 나가지 않게 — Tab 은 썸네일 · 확인 단추 사이만 돈다. Esc 는 무시한다.
    function cycleFocus(back) {
      var list = Array.prototype.slice.call(root.querySelectorAll('[data-foms-notice-thumb], [data-foms-notice-ok]'));
      var at = list.indexOf(document.activeElement);
      var next = back ? (at <= 0 ? list.length - 1 : at - 1) : (at + 1) % list.length;
      (list[next] || ok).focus();
    }
    function onFocusIn(ev) {
      if (higherOpen() || root.contains(ev.target)) return;
      ok.focus();
    }
    function onKeyDown(ev) {
      if (higherOpen()) return;
      if (ev.key === 'Tab' && root.contains(ev.target)) { // 썸네일 · 확인 단추 사이만 돈다
        ev.preventDefault();
        ev.stopPropagation();
        cycleFocus(ev.shiftKey);
        return;
      }
      if (ev.key === 'Escape' || ev.key === 'Esc' || ev.key === 'Tab' || !root.contains(ev.target)) {
        ev.preventDefault();
        ev.stopPropagation();
        ok.focus();
      }
    }

    function show(notice) {
      if (title) title.textContent = notice.title || '';
      if (body) body.textContent = notice.body || '';
      if (meta) meta.textContent = [notice.created_by_name, notice.created_at].filter(Boolean).join(' · ');
      if (images) {
        if (window.FomsNoticeGallery) window.FomsNoticeGallery.render(images, notice.images);
        else images.hidden = true;
      }
      if (count) count.textContent = total > 1 ? (index + 1) + ' / ' + total : '';
      if (status) { status.textContent = ''; status.classList.remove('is-error'); }
      ok.focus();
    }

    function close() {
      document.removeEventListener('focusin', onFocusIn, true);
      document.removeEventListener('keydown', onKeyDown, true);
      root.hidden = true;
      document.documentElement.classList.remove('foms-notice-open');
    }

    function advance(next) {
      queue = next;
      if (!queue.length) { close(); return; }
      index += 1;
      total = Math.max(total, index + queue.length);
      show(queue[0]);
    }

    ok.addEventListener('click', async function () {
      var current = queue[0];
      if (!current) return;
      ok.disabled = true;
      try {
        var result = await postJson(idUrl(ackUrl, current.id));
        if (result.ok) {
          if (result.data.unread != null) setBadges(result.data.unread);
          advance(Array.isArray(result.data.pending) ? result.data.pending : []);
        } else {
          // 그새 지운 · 끝난 · 대상이 바뀐 공지 — 남은 차례에서 빼고 넘어간다.
          advance(queue.filter(function (n) { return String(n.id) !== String(current.id); }));
        }
      } catch (err) {
        if (status) { status.textContent = err.message; status.classList.add('is-error'); }
      }
      ok.disabled = false;
    });

    document.addEventListener('focusin', onFocusIn, true);
    document.addEventListener('keydown', onKeyDown, true);
    root.hidden = false;
    document.documentElement.classList.add('foms-notice-open');
    show(queue[0]);
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
      // 서버가 정한 차례(확인 안 한 창 공지, 오래된 것부터 최대 5)를 그대로 띄운다.
      var pending = Array.isArray(data.data.pending) ? data.data.pending.filter(Boolean) : [];
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
        var result = await postJson(idUrl(readUrl, item.getAttribute('data-notice-id')));
        if (!result.ok) return; // 그새 끝난 공지 — 다시 남길 것이 없다
        item.classList.remove('is-unread');
        var label = item.querySelector('[data-foms-notice-unread-label]');
        if (label) label.remove();
        var counter = list.querySelector('[data-foms-notice-unread-count]');
        var left = result.data.unread;
        setBadges(left != null ? left : Math.max((counter ? Number(counter.textContent) || 0 : 1) - 1, 0));
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
